import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'overview',
    {
      type: 'category',
      label: 'Concepts',
      items: [
        'concepts/workspace-and-cohorts',
        'concepts/patient-vs-sample',
      ],
    },
    {
      type: 'category',
      label: 'User Guide',
      items: [
        'user-guide/datasets',
        'user-guide/dashboard',
        'user-guide/query',
        'user-guide/saved-cohorts-and-handoffs',
        'user-guide/analysis',
        'user-guide/pheno-ranker',
        'user-guide/user-journeys',
      ],
    },
    {
      type: 'category',
      label: 'Admin Guide',
      items: [
        'admin-guide/datasets-and-access',
        'admin-guide/local-auth-and-groups',
        'admin-guide/model-providers',
      ],
    },
    {
      type: 'category',
      label: 'Developer Guide',
      items: [
        'developer-guide/architecture',
        'developer-guide/design-decisions',
        'developer-guide/query-disclosure-modes',
        'developer-guide/state-and-persistence',
        'developer-guide/api-reference',
      ],
    },
  ],
};

export default sidebars;
