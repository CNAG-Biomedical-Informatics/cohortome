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
        'user-guide/query',
        'user-guide/analysis',
        'user-guide/pheno-ranker',
      ],
    },
    {
      type: 'category',
      label: 'Admin Guide',
      items: [
        'admin-guide/datasets-and-access',
      ],
    },
    {
      type: 'category',
      label: 'Developer Guide',
      items: [
        'developer-guide/architecture',
      ],
    },
  ],
};

export default sidebars;
