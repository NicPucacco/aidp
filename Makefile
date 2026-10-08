SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

CLUSTER_NAME ?= aidp
KUBE_CONTEXT ?= kind-$(CLUSTER_NAME)
TF_DIR       := terraform/argocd
TF           := terraform -chdir=$(TF_DIR)
# Argo CD tracks whatever is checked out: a phase tag if HEAD is exactly on
# one, otherwise the current branch. It must exist on GitHub (Argo CD pulls
# from there, not from your working copy).
TARGET_REVISION ?= $(shell git describe --tags --exact-match 2>/dev/null || git rev-parse --abbrev-ref HEAD)
TF_VARS      := -var kube_context=$(KUBE_CONTEXT) -var target_revision=$(TARGET_REVISION)

.PHONY: help
help: ## Show targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: doctor
doctor: ## Check required tools are installed
	@scripts/doctor.sh

.PHONY: up
up: doctor cluster platform wait ## Create a local kind cluster and install the platform

.PHONY: cluster
cluster: ## Create the local kind cluster (skip this to use your own cluster)
	@kind get clusters 2>/dev/null | grep -qx $(CLUSTER_NAME) \
		|| kind create cluster --config bootstrap/kind/cluster.yaml

.PHONY: platform
platform: ## Install the platform onto KUBE_CONTEXT (any conformant cluster)
	$(TF) init -input=false
	$(TF) apply -input=false -auto-approve $(TF_VARS)

.PHONY: wait
wait: ## Wait until every Argo CD application is Synced and Healthy
	KUBE_CONTEXT=$(KUBE_CONTEXT) scripts/wait-for-platform.sh

# --- AKS (production) --------------------------------------------------------
# Needs `az login`, terraform/aks/backend.hcl and terraform/aks/terraform.tfvars
# (copy the .example files). See terraform/README.md.
AKS_TF := terraform -chdir=terraform/aks

.PHONY: aks-plan
aks-plan: ## Plan the AKS cluster (production)
	$(AKS_TF) init -input=false -backend-config=backend.hcl
	$(AKS_TF) plan -input=false -out=aks.tfplan

.PHONY: aks-apply
aks-apply: ## Apply the reviewed AKS plan from aks-plan
	$(AKS_TF) apply -input=false aks.tfplan

.PHONY: aks-test
aks-test: ## Offline plan tests for the AKS module (mocked providers, no Azure access)
	$(AKS_TF) init -backend=false -input=false >/dev/null
	$(AKS_TF) test

.PHONY: ui
ui: ## Port-forward the Argo CD UI to http://localhost:8080
	kubectl --context $(KUBE_CONTEXT) -n argocd port-forward svc/argocd-server 8080:80

.PHONY: gateway
gateway: ## Port-forward the Gateway: http://backstage.localhost:8000, http://argocd.localhost:8000
	kubectl --context $(KUBE_CONTEXT) -n envoy-gateway-system port-forward \
		$$(kubectl --context $(KUBE_CONTEXT) -n envoy-gateway-system get svc \
			-l gateway.envoyproxy.io/owning-gateway-name=platform -o name) 8000:80

.PHONY: portal-image
portal-image: ## Build the portal image for the committed portal/ tree and load it into kind
	CLUSTER=$(CLUSTER_NAME) scripts/portal-image.sh build

.PHONY: portal-token
portal-token: ## Let golden-path templates open real PRs (uses GITHUB_TOKEN or your gh login)
	@token=$${GITHUB_TOKEN:-$$(gh auth token)}; \
	kubectl --context $(KUBE_CONTEXT) -n backstage create secret generic backstage-github \
		--from-literal=token="$$token" --dry-run=client -o yaml | kubectl --context $(KUBE_CONTEXT) apply -f -; \
	kubectl --context $(KUBE_CONTEXT) -n backstage rollout restart deploy/backstage

.PHONY: agent-setup
agent-setup: ## Install the platform MCP server for .mcp.json (Claude Code and other MCP clients)
	python3 -m venv agents/platform-mcp/.venv
	agents/platform-mcp/.venv/bin/pip install -q -e 'agents/platform-mcp[test]'
	@echo "Ready. Open this repo in an MCP client; see docs/agents.md for PR identity setup."

.PHONY: test-agents
test-agents: ## MCP server unit tests, then agent proposals through the tenant gate
	agents/platform-mcp/.venv/bin/pytest -q agents/platform-mcp
	PATH=agents/platform-mcp/.venv/bin:$$PATH scripts/test-agent-proposals.py

.PHONY: password
password: ## Print the initial Argo CD admin password
	@kubectl --context $(KUBE_CONTEXT) -n argocd get secret argocd-initial-admin-secret \
		-o jsonpath='{.data.password}' | base64 -d; echo

.PHONY: status
status: ## Show Argo CD application health
	kubectl --context $(KUBE_CONTEXT) -n argocd get applications

.PHONY: down
down: ## Delete the local kind cluster
	kind delete cluster --name $(CLUSTER_NAME)
	rm -f $(TF_DIR)/terraform.tfstate $(TF_DIR)/terraform.tfstate.backup

.PHONY: lint
lint: ## Run the same static checks as CI
	$(TF) fmt -check -recursive
	$(TF) init -backend=false -input=false >/dev/null
	$(TF) validate
	yamllint -s .
	helm lint platform/apps

.PHONY: generate
generate: ## Regenerate catalog/apis.yaml from the XRDs
	scripts/gen-catalog.py

.PHONY: test-apis
test-apis: ## Render XRs through the real Compositions (needs Docker + crossplane CLI)
	scripts/gen-catalog.py --check
	pytest -q platform/apis

.PHONY: check-tenants
check-tenants: ## Render tenant config through real compositions and evaluate policies
	scripts/check-tenants.py

.PHONY: test-templates
test-templates: ## Render golden-path templates and run the output through the tenant gate
	scripts/test-templates.py

.PHONY: test
test: test-apis check-tenants test-templates test-agents ## All tests: unit, tenant render+policy, then live-cluster checks
	kyverno test platform/policies/tests --detailed-results
	KUBE_CONTEXT=$(KUBE_CONTEXT) scripts/e2e-admission.sh
	KUBE_CONTEXT=$(KUBE_CONTEXT) scripts/e2e-database.sh
	KUBE_CONTEXT=$(KUBE_CONTEXT) scripts/e2e-webservice.sh
