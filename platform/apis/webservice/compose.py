"""Compose a Fernhill WebService into a Deployment, Service, and optional HTTPRoute.

This file is the source of truth. scripts/gen-compositions.py embeds it into
composition.yaml for function-python to run; CI fails if the two drift.

Everything a team would otherwise have to remember (probes, limits, a
non-root security context, a disruption budget, spreading replicas) is
decided here once, so every WebService gets it.
"""

from crossplane.function import resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

SIZES = {
    "small": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"memory": "256Mi"}},
    "medium": {"requests": {"cpu": "250m", "memory": "512Mi"}, "limits": {"memory": "512Mi"}},
    "large": {"requests": {"cpu": "1", "memory": "2Gi"}, "limits": {"memory": "2Gi"}},
}

# Runs as a fixed non-root UID. Images that declare a named USER can't be
# verified as non-root by the kubelet, so the platform pins one.
RUN_AS = 10001

GATEWAY = {"name": "platform", "namespace": "gateway"}

# The Database API's contract (status.connectionSecret): CloudNativePG writes
# these keys to "<database>-app".
PG_ENV = {
    "DATABASE_URL": "uri",
    "PGHOST": "host",
    "PGPORT": "port",
    "PGDATABASE": "dbname",
    "PGUSER": "user",
    "PGPASSWORD": "password",
}


def compose(req: fnv1.RunFunctionRequest, rsp: fnv1.RunFunctionResponse):
    xr = resource.struct_to_dict(req.observed.composite.resource)
    name = xr["metadata"]["name"]
    team = xr["metadata"]["namespace"]
    spec = xr.get("spec", {})
    port = spec.get("port", 8080)
    replicas = spec.get("replicas", 2)
    labels = {
        "app.kubernetes.io/name": name,
        # Team namespaces are named after the team (ADR-0007).
        "platform.fernhill.io/owner": team,
    }
    selector = {"app.kubernetes.io/name": name}

    resource.update(rsp.desired.resources["deployment"], _deployment(name, labels, selector, spec, port, replicas))
    resource.update(rsp.desired.resources["service"], _service(name, labels, selector, port))
    rsp.desired.resources["service"].ready = fnv1.READY_TRUE

    if replicas > 1:
        resource.update(rsp.desired.resources["pdb"], _pdb(name, labels, selector))
        rsp.desired.resources["pdb"].ready = fnv1.READY_TRUE

    status = {}
    if spec.get("expose", False):
        host = f"{name}.{team}.localhost"
        resource.update(rsp.desired.resources["route"], _route(name, labels, host))
        rsp.desired.resources["route"].ready = fnv1.READY_TRUE
        status["url"] = f"http://{host}"
    if spec.get("database"):
        status["databaseSecret"] = f"{spec['database']}-app"
    if status:
        resource.update(rsp.desired.composite, {"status": status})

    if _deployment_available(req):
        rsp.desired.resources["deployment"].ready = fnv1.READY_TRUE


def _deployment(name, labels, selector, spec, port, replicas):
    env = [{"name": e["name"], "value": e["value"]} for e in spec.get("env", [])]
    if spec.get("database"):
        secret = f"{spec['database']}-app"
        env += [
            {"name": var, "valueFrom": {"secretKeyRef": {"name": secret, "key": key}}}
            for var, key in PG_ENV.items()
        ]

    probe = {"httpGet": {"path": spec.get("healthPath", "/healthz"), "port": "http"}}
    pod_spec = {
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": RUN_AS,
            "runAsGroup": RUN_AS,
            "fsGroup": RUN_AS,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": "app",
                "image": spec["image"],
                "ports": [{"name": "http", "containerPort": port}],
                "env": env,
                "resources": SIZES[spec.get("size", "small")],
                "readinessProbe": {**probe, "periodSeconds": 5},
                "livenessProbe": {**probe, "periodSeconds": 10, "failureThreshold": 6},
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "readOnlyRootFilesystem": True,
                    "capabilities": {"drop": ["ALL"]},
                },
                "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
            }
        ],
        "volumes": [{"name": "tmp", "emptyDir": {}}],
    }
    if replicas > 1:
        pod_spec["topologySpreadConstraints"] = [
            {
                "maxSkew": 1,
                "topologyKey": "kubernetes.io/hostname",
                # Prefer spreading; don't block scheduling on a 1-node cluster.
                "whenUnsatisfiable": "ScheduleAnyway",
                "labelSelector": {"matchLabels": selector},
            }
        ]

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "labels": labels},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": selector},
            "template": {"metadata": {"labels": labels}, "spec": pod_spec},
        },
    }


def _service(name, labels, selector, port):
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "labels": labels},
        "spec": {
            "selector": selector,
            "ports": [{"name": "http", "port": 80, "targetPort": "http"}],
        },
    }


def _pdb(name, labels, selector):
    return {
        "apiVersion": "policy/v1",
        "kind": "PodDisruptionBudget",
        "metadata": {"name": name, "labels": labels},
        "spec": {"maxUnavailable": 1, "selector": {"matchLabels": selector}},
    }


def _route(name, labels, host):
    return {
        "apiVersion": "gateway.networking.k8s.io/v1",
        "kind": "HTTPRoute",
        "metadata": {"name": name, "labels": labels},
        "spec": {
            "parentRefs": [GATEWAY],
            "hostnames": [host],
            "rules": [{"backendRefs": [{"name": name, "port": 80}]}],
        },
    }


def _deployment_available(req: fnv1.RunFunctionRequest) -> bool:
    if "deployment" not in req.observed.resources:
        return False
    observed = resource.struct_to_dict(req.observed.resources["deployment"].resource)
    conditions = observed.get("status", {}).get("conditions", [])
    return any(c.get("type") == "Available" and c.get("status") == "True" for c in conditions)
