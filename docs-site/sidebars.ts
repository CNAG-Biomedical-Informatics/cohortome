import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'overview',
    {
      type: 'category',
      label: 'Project',
      items: [
        'project/3tr-and-precisesads',
        'project/scope-and-boundaries',
      ],
    },
    {
      type: 'category',
      label: 'Concepts',
      items: [
        'concepts/workspace-and-cohorts',
        'concepts/patient-vs-sample',
        'concepts/cross-sectional-and-longitudinal',
        'concepts/assays-and-modalities',
        'concepts/governed-ai',
      ],
    },
    {
      type: 'category',
      label: 'User Guide',
      items: [
        'user-guide/datasets',
        'user-guide/synthetic-autoimmune-demo',
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
        'admin-guide/starting-and-stopping',
        'admin-guide/datasets-and-access',
        'admin-guide/local-auth-and-groups',
        'admin-guide/model-providers',
        'admin-guide/dicom-viewing',
        'admin-guide/real-data-security',
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
    {
      type: 'category',
      label: 'Validation',
      items: [
        'validation/evaluation-and-evidence',
      ],
    },
    {
      type: 'category',
      label: 'About',
      items: [
        'about/faq',
        'about/citation-and-funding',
      ],
    },
  ],
};

export default sidebars;
