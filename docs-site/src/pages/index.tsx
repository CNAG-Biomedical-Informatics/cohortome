import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';

import styles from './index.module.css';

const researchPaths = [
  {
    label: 'Explore',
    title: 'See each patient over time',
    body: 'Check clinical records, linked samples, assay coverage, and collection dates.',
    to: '/docs/user-guide/dashboard',
  },
  {
    label: 'Cohorts',
    title: 'Find and save patient groups',
    body: 'Search by disease, treatment, or other recorded fields. Save matching patients as a cohort.',
    to: '/docs/user-guide/query',
  },
  {
    label: 'Analysis',
    title: 'Run an analysis',
    body: 'Select a method and its inputs. Inspect plots, tables, parameters, and output files.',
    to: '/docs/user-guide/analysis',
  },
  {
    label: 'Pheno-Ranker',
    title: 'Compare patient phenotypes',
    body: 'Compare records using Hamming distance or Jaccard similarity, then inspect rankings and plots.',
    to: '/docs/user-guide/pheno-ranker',
  },
];

export default function Home() {
  const workspaceScreenshot = useBaseUrl('/img/screenshots/workspace-shell.png');

  return (
    <Layout
      title="COHORTome"
      description="Software for exploring clinical and multimodal data, defining cohorts, and running analyses.">
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>AI-assisted clinical and multimodal research</p>
            <h1 className={styles.heroWordmark} aria-label="COHORTome">
              <span className={styles.heroWordmarkPrimary}>COHORT</span>
              <span className={styles.heroWordmarkSecondary}>ome</span>
            </h1>
            <p className={styles.heroLead}>
              Explore clinical and multimodal data, define patient cohorts,
              and run analyses. Desktop is the recommended installation
              for individual use.
            </p>
            <div className={styles.heroActions}>
              <Link className="button button--primary" to="/docs/getting-started/desktop">
                Desktop
              </Link>
              <Link className="button button--outline button--secondary" to="/docs/user-guide/user-journeys">
                User guide
              </Link>
            </div>
            <p className={styles.heroModelNote}>Optional language models help interpret questions and explain results.</p>
            </div>
            <figure className={styles.heroPreview}>
              <a href={workspaceScreenshot} target="_blank" rel="noopener noreferrer" aria-label="View the COHORTome workspace screenshot at full size (opens a new tab)">
                <img
                  src={workspaceScreenshot}
                  width="1440"
                  height="1000"
                  alt="COHORTome dashboard showing synthetic patient summaries and charts, with chats and navigation on the left."
                  fetchPriority="high"
                />
              </a>
              <figcaption>Synthetic demo workspace <span aria-hidden="true">↗</span> <span className={styles.previewHint}>View full size</span></figcaption>
            </figure>
          </div>
        </section>


        <section className={styles.pathsSection}>
          <div className={styles.inner}>
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.sectionLabel}>Documentation</p>
                <h2>Using COHORTome</h2>
              </div>
              <p>
                Follow a short guide for the task you want to try.
              </p>
            </div>
            <div className={styles.pathGrid}>
              {researchPaths.map((path) => (
                <Link className={styles.pathCard} key={path.label} to={path.to}>
                  <span>{path.label}</span>
                  <h3>{path.title}</h3>
                  <p>{path.body}</p>
                  <strong>Read the guide <span aria-hidden="true">→</span></strong>
                </Link>
              ))}
            </div>
          </div>
        </section>

        <aside className={styles.teamNote}>
          <div className={styles.inner}>
            <p><strong>Web is recommended only for centralized, multi-user deployments with dataset permissions.</strong> See the <Link to="/docs/admin-guide/starting-and-stopping">administrator's deployment guide</Link>.</p>
          </div>
        </aside>
      </main>
    </Layout>
  );
}
