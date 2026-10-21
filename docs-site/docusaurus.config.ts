import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import type * as Redocusaurus from 'redocusaurus';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'COHORTome',
  tagline: 'Open-source workspace for integrated clinical and multimodal cohort research',
  favicon: 'img/cohortome-logo.svg',
  markdown: {
    mermaid: true,
  },
  themes: ['@docusaurus/theme-mermaid'],

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://cnag-biomedical-informatics.github.io',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/cohortome/',

  // GitHub pages deployment config.
  // If you aren't using GitHub pages, you don't need these.
  organizationName: 'CNAG-Biomedical-Informatics',
  projectName: 'cohortome',

  onBrokenLinks: 'throw',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl:
            'https://github.com/CNAG-Biomedical-Informatics/cohortome/tree/main/docs-site/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
    [
      'redocusaurus',
      {
        specs: [
          {
            spec: 'static/openapi/cohortome-openapi.json',
            route: '/api/',
          },
        ],
        theme: {
          primaryColor: '#0e6964',
        },
      },
    ] satisfies Redocusaurus.PresetEntry,
  ],

  themeConfig: {
    image: 'img/screenshots/workspace-shell.png',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'COHORTome',
      logo: {
        alt: 'COHORTome',
        src: 'img/cohortome-logo.svg',
      },
      items: [
        {
          to: '/docs/overview',
          label: 'Docs',
          position: 'left',
        },
        {
          to: '/docs/getting-started/desktop',
          position: 'left',
          label: 'Installation',
        },
        {
          to: '/docs/user-guide/user-journeys',
          label: 'User guide',
          position: 'left',
        },
        {
          href: 'https://github.com/CNAG-Biomedical-Informatics/cohortome',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {
              label: 'Overview',
              to: '/docs/overview',
            },
            {
              label: 'Desktop',
              to: '/docs/getting-started/desktop',
            },
            {
              label: 'Web deployment',
              to: '/docs/admin-guide/starting-and-stopping',
            },
            {
              label: 'DICOM viewing',
              to: '/docs/admin-guide/dicom-viewing',
            },
          ],
        },
        {
          title: 'Project',
          items: [
            {
              label: 'Scope and boundaries',
              to: '/docs/project/scope-and-boundaries',
            },
            {
              label: 'Citation',
              to: '/docs/about/citation-and-funding',
            },
            {
              label: 'Acknowledgements',
              to: '/docs/about/acknowledgements',
            },
          ],
        },
        {
          title: 'Open Source',
          items: [
            {
              label: 'Repository',
              href: 'https://github.com/CNAG-Biomedical-Informatics/cohortome',
            },
            {
              label: 'API',
              to: '/api/',
            },
            {
              label: 'Apache License 2.0',
              href: 'https://github.com/CNAG-Biomedical-Informatics/cohortome/blob/main/LICENSE',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Manuel Rueda - CNAG. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
