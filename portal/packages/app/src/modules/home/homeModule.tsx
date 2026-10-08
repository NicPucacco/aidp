import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { HomePageWidgetBlueprint } from '@backstage/plugin-home-react/alpha';
import { MarkdownContent } from '@backstage/core-components';

const content = `
## Fernhill Developer Portal

Everything here is a view over Git. Nothing in this portal changes the
cluster directly: **templates open pull requests** against the platform
repo, and CI checks them before anyone reviews them.

### Golden paths

- **[New web service](/create)**: a pinned image, probes, limits, a route,
  and optionally a Postgres database. About ten lines of YAML, in a PR.
- **[New database](/create)**: a t-shirt-sized Postgres with credentials
  your service can reference.

### Find things

- **[Catalog](/catalog)**: every service, database, and team, with what's
  running in Kubernetes right now.
- **[Platform APIs](/api-docs)**: the \`WebService\` and \`Database\` schemas.

### Why it works this way

The [ADRs](https://github.com/NicPucacco/aidp/tree/main/docs/adr) explain
each decision, starting with
[ADR-0001: the pull request is the platform API](https://github.com/NicPucacco/aidp/blob/main/docs/adr/0001-the-pull-request-is-the-platform-api.md).
`;

const gettingStartedWidget = HomePageWidgetBlueprint.make({
  name: 'getting-started',
  params: {
    name: 'GettingStarted',
    title: 'Welcome',
    description: 'How the Fernhill platform works',
    components: async () => ({
      Content: () => <MarkdownContent content={content} />,
    }),
  },
});

export const homeModule = createFrontendModule({
  pluginId: 'home',
  extensions: [gettingStartedWidget],
});
