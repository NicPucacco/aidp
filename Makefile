SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

CLUSTER_NAME ?= aidp
KUBE_CONTEXT ?= kind-$(CLUSTER_NAME)
TF_DIR       := bootstrap/terraform
TF           := terraform -chdir=$(TF_DIR)
TF_VARS      := -var kube_context=$(KUBE_CONTEXT)

.PHONY: help
help: ## Show targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: doctor
doctor: ## Check required tools are installed
	@scripts/doctor.sh

.PHONY: up
up: doctor cluster platform ## Create a local kind cluster and install the platform

.PHONY: cluster
cluster: ## Create the local kind cluster (skip this to use your own cluster)
	@kind get clusters 2>/dev/null | grep -qx $(CLUSTER_NAME) \
		|| kind create cluster --config bootstrap/kind/cluster.yaml

.PHONY: platform
platform: ## Install the platform onto KUBE_CONTEXT (any conformant cluster)
	$(TF) init -input=false
	$(TF) apply -input=false -auto-approve $(TF_VARS)

.PHONY: ui
ui: ## Port-forward the Argo CD UI to http://localhost:8080
	kubectl --context $(KUBE_CONTEXT) -n argocd port-forward svc/argocd-server 8080:80

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
