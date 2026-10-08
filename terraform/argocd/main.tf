# Day-0 bootstrap. Terraform's job ends once Argo CD is running and pointed at
# platform/. Everything after that is reconciled from Git (ADR-0003).

provider "helm" {
  kubernetes = {
    config_path    = pathexpand(var.kubeconfig_path)
    config_context = var.kube_context
  }
}

locals {
  argocd_namespace = "argocd"
}

resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = var.argocd_chart_version
  namespace        = local.argocd_namespace
  create_namespace = true
  wait             = true
  timeout          = 600

  values = [file("${path.module}/../../platform/argocd/values.yaml")]

  # Day 0 only. From v1 the platform/apps tree manages Argo CD's chart version
  # and values, so a later `terraform apply` must not fight it (ADR-0003).
  lifecycle {
    ignore_changes = [version, values]
  }
}

# The root Application is wrapped in the argocd-apps chart rather than a
# kubernetes_manifest resource: kubernetes_manifest needs the Application CRD
# at plan time, which doesn't exist on a fresh cluster.
resource "helm_release" "root_app" {
  name       = "argocd-root"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argocd-apps"
  version    = var.argocd_apps_chart_version
  namespace  = local.argocd_namespace

  values = [yamlencode({
    applications = {
      root = {
        namespace  = local.argocd_namespace
        project    = "default"
        finalizers = ["resources-finalizer.argocd.argoproj.io"]
        source = {
          repoURL        = var.repo_url
          targetRevision = var.target_revision
          path           = "platform/apps"
          # Child apps track the same repo and revision as the root, so a
          # PR's CI run tests the PR's whole tree, not main's children.
          helm = {
            # environment: null keeps the chart's local (kind) defaults; on
            # AKS it's terraform/aks's platform_environment output (ADR-0017).
            valuesObject = merge(
              {
                repoURL        = var.repo_url
                targetRevision = var.target_revision
              },
              { for k, v in { environment = var.platform_environment } : k => v if v != null },
            )
          }
        }
        destination = {
          server    = "https://kubernetes.default.svc"
          namespace = local.argocd_namespace
        }
        syncPolicy = {
          automated   = { prune = true, selfHeal = true }
          syncOptions = ["CreateNamespace=true"]
        }
      }
    }
  })]

  depends_on = [helm_release.argocd]
}
