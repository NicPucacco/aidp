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

  values = [file("${path.module}/values/argocd.yaml")]
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
          directory      = { recurse = true }
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
