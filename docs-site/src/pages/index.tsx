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
    label: 'Query',
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
              Find patients with the clinical characteristics and assay data
              you need. Save them as a cohort and run analyses in the same workspace.
            </p>
            <div className={styles.heroActions}>
              <Link className="button button--primary" to="/docs/getting-started/desktop">
                Install Desktop <span aria-hidden="true">↓</span>
              </Link>
              <Link className="button button--outline button--secondary" to="/docs/user-guide/user-journeys">
                Try a demo <span aria-hidden="true">→</span>
              </Link>
            </div>
            <p className={styles.platforms}>Linux · macOS · Windows</p>
            <p className={styles.heroModelNote}>Connect an optional language model for help with queries and analysis.</p>
            </div>
            <figure className={styles.heroPreview}>
              <div className={styles.previewHeader}><span>The workspace</span><span>Desktop & Web</span></div>
              <a href={workspaceScreenshot} target="_blank" rel="noopener noreferrer" aria-label="View the COHORTome workspace screenshot at full size (opens a new tab)">
                <img
                  src={workspaceScreenshot}
                  width="1440"
                  height="1000"
                  alt="COHORTome dashboard showing synthetic patient summaries and charts, with chats and navigation on the left."
                  fetchPriority="high"
                />
              </a>
              <figcaption><span>Synthetic demo data</span><a href={workspaceScreenshot} target="_blank" rel="noopener noreferrer">View full size <span aria-hidden="true">↗</span></a></figcaption>
            </figure>
          </div>
        </section>


        <section className={styles.pathsSection}>
          <div className={styles.inner}>
            <div className={styles.sectionHeading}>
              <div>
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
                  <h3>{path.title} <span aria-hidden="true">↗</span></h3>
                  <p>{path.body}</p>
                </Link>
              ))}
            </div>
            <p className={styles.videoNote}>
              <a href="https://www.youtube.com/playlist?list=PLITMLc8FnGyQ">Video tutorials on YouTube <span aria-hidden="true">↗</span></a>
            </p>
          </div>
        </section>

        <aside className={styles.deploymentSection} aria-label="Choose a deployment">
          <div className={styles.deploymentPanel}>
            <div><h2>Desktop for individual research</h2><p>Install the app and work with datasets on your computer.</p><Link to="/docs/getting-started/desktop">Desktop installation →</Link></div>
            <div><h2>Web for research teams</h2><p>Deploy from Docker Hub with user accounts, shared data and dataset permissions.</p><Link to="/docs/admin-guide/starting-and-stopping">Web deployment →</Link></div>
          </div>
        </aside>
      </main>
    </Layout>
  );
}
