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
        {type: 'category', label: 'Datasets', collapsed: false, link: {type: 'doc', id: 'user-guide/datasets'}, items: [
          'user-guide/included-datasets',
          'user-guide/downloadable-datasets',
          'user-guide/fetch-datasets',
          {type: 'doc', id: 'concepts/assays-and-modalities', label: 'Supported data and modalities'},
          'user-guide/install-datasets',
        ]},
        {type: 'category', label: 'Explore and build cohorts', items: [
          'user-guide/dashboard',
          'user-guide/query',
          'user-guide/saved-cohorts-and-handoffs',
        ]},
        {type: 'category', label: 'Analysis', items: [
          'user-guide/analysis',
          'user-guide/pheno-ranker',
        ]},
      ],
    },
    {
      type: 'category',
      label: 'Advanced',
      collapsed: true,
      items: [
        'admin-guide/starting-and-stopping',
        'admin-guide/local-auth-and-groups',
        {type: 'doc', id: 'admin-guide/datasets-and-access', label: 'Dataset configuration'},
        {type: 'doc', id: 'admin-guide/model-providers', label: 'Model configuration'},
        {type: 'doc', id: 'admin-guide/dicom-viewing', label: 'Imaging setup'},
        {type: 'category', label: 'Prepare and contribute datasets', collapsed: true, items: [
          'admin-guide/prepare-datasets', 'admin-guide/dataset-packages',
          'admin-guide/dataset-review-checklist',
        ]},
        {type: 'category', label: 'Deployment details', collapsed: true, items: [
          'admin-guide/native-installation', 'admin-guide/institutional-sign-in',
          'admin-guide/model-deployment', 'admin-guide/dataset-registration-reference',
        ]},
        'developer-guide/technical-reference',
      ],
    },
    {
      type: 'category',
      label: 'Help',
      items: [
        'video-tutorials',
        'about/faq',
        'about/citation',
        'about/acknowledgements',
      ],
    },
  ],
};

export default sidebars;
