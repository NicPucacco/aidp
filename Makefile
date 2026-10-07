SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

CLUSTER_NAME ?= aidp
KUBE_CONTEXT ?= kind-$(CLUSTER_NAME)
TF_DIR       := bootstrap/terraform
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

.PHONY: ui
ui: ## Port-forward the Argo CD UI to http://localhost:8080
	kubectl --context $(KUBE_CONTEXT) -n argocd port-forward svc/argocd-server 8080:80

.PHONY: gateway
gateway: ## Port-forward the platform Gateway; then open http://argocd.localhost:8000
	kubectl --context $(KUBE_CONTEXT) -n envoy-gateway-system port-forward \
		$$(kubectl --context $(KUBE_CONTEXT) -n envoy-gateway-system get svc \
			-l gateway.envoyproxy.io/owning-gateway-name=platform -o name) 8000:80

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
generate: ## Regenerate compositions from their compose.py
	scripts/gen-compositions.py

.PHONY: test-apis
test-apis: ## Unit-test composition functions (needs: pip install -r platform/apis/requirements-dev.txt)
	scripts/gen-compositions.py --check
	pytest -q platform/apis

.PHONY: test
test: test-apis ## All tests: API unit tests, policy tests, then live-cluster checks
	kyverno test platform/policies/tests --detailed-results
	KUBE_CONTEXT=$(KUBE_CONTEXT) scripts/e2e-admission.sh
	KUBE_CONTEXT=$(KUBE_CONTEXT) scripts/e2e-database.sh
