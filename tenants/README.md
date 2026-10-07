# tenants

Tenant configuration: one directory per team, one subdirectory per service.
This is the part of the repo that developers (through Backstage) and AI agents
(through the platform MCP server) write to, always by pull request
([ADR-0001](../docs/adr/0001-the-pull-request-is-the-platform-api.md)).

```
tenants/
  billing/
    invoice-api/
      service.yaml     # Service API (v3)
      database.yaml    # Database API (v2)
      catalog-info.yaml
```

Populated from `v2-database-path`.
