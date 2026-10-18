import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'overview',
    'getting-started/desktop',
    {
      type: 'category',
      label: 'User guide',
      items: [
        'user-guide/user-journeys',
        'user-guide/datasets',
        'user-guide/synthetic-autoimmune-demo',
        'user-guide/dashboard',
        'user-guide/query',
        'user-guide/saved-cohorts-and-handoffs',
        'user-guide/analysis',
        'user-guide/pheno-ranker',
      ],
    },
    {
      type: 'category',
      label: 'Advanced',
      collapsed: true,
      items: [
        'admin-guide/starting-and-stopping',
        {type: 'doc', id: 'admin-guide/datasets-and-access', label: 'Dataset configuration'},
        {type: 'doc', id: 'admin-guide/model-providers', label: 'Model configuration'},
        {type: 'doc', id: 'admin-guide/dicom-viewing', label: 'Imaging setup'},
        'developer-guide/technical-reference',
      ],
    },
    {
      type: 'category',
      label: 'About',
      items: [
        'about/faq',
        'about/citation-and-funding',
        'about/acknowledgements',
      ],
    },
  ],
};

export default sidebars;
