import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';

import styles from './index.module.css';

export default function Home() {
  const {siteConfig} = useDocusaurusContext();
  const logoUrl = useBaseUrl('/img/patient-navigator-logo.png');

  return (
    <Layout
      title={siteConfig.title}
      description="Documentation for Patient Navigator workspace, analysis, and administration.">
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.heroGrid}>
            <div className={styles.copy}>
              <p className={styles.kicker}>Patient Navigator</p>
              <h1>Clinical research workbench.</h1>
              <p className={styles.lede}>
                Patient Navigator combines dataset governance, cohort discovery,
                analysis workflows, phenotypic similarity, and controlled AI
                provider access in one local-first clinical workbench.
              </p>
              <div className={styles.actions}>
                <Link className="button button--primary button--lg" to="/docs/overview">
                  Start with the workflow
                </Link>
                <Link className="button button--secondary button--lg" to="/docs/user-guide/analysis">
                  Run analyses
                </Link>
                <Link className="button button--secondary button--lg" to="/docs/admin-guide/datasets-and-access">
                  Configure data access
                </Link>
              </div>
            </div>

            <div className={styles.flowCard} aria-label="Patient Navigator workspace flow">
              <Link className={styles.identity} to="/docs/overview">
                <img className={styles.heroLogo} src={logoUrl} alt="Patient Navigator logo" />
                <span>Patient Navigator</span>
              </Link>
              <div className={styles.flow}>
                <div>
                  <span>Input</span>
                  <strong>BFF clinical data + transcriptomics matrices</strong>
                </div>
                <div className={styles.arrow}>-&gt;</div>
                <div className={styles.centerModel}>
                  <span>Workspace</span>
                  <strong>Datasets, cohorts, analysis chats, jobs</strong>
                </div>
                <div className={styles.arrow}>-&gt;</div>
                <div>
                  <span>Output</span>
                  <strong>Query results, plots, workflows, Pheno-Ranker views</strong>
                </div>
              </div>
              <div className={styles.tokens}>
                <span>local auth</span>
                <span>OIDC</span>
                <span>DuckDB stores</span>
                <span>LLM providers</span>
              </div>
            </div>
          </div>
        </section>

        <section className={styles.sections}>
          <div className={styles.grid}>
            <Link className={styles.card} to="/docs/user-guide/datasets">
              <span>Workspace</span>
              <h2>Select data</h2>
              <p>Understand default startup loading, on-demand datasets, and workspace reload behavior.</p>
            </Link>
            <Link className={styles.card} to="/docs/user-guide/query">
              <span>Cohorts</span>
              <h2>Build subsets</h2>
              <p>Use deterministic and LLM-planned Query flows before saving reusable cohorts.</p>
            </Link>
            <Link className={styles.card} to="/docs/user-guide/analysis">
              <span>Analysis</span>
              <h2>Interpret results</h2>
              <p>Run quick prompts, catalog tools, workflows, plots, and background jobs.</p>
            </Link>
            <Link className={styles.card} to="/docs/user-guide/pheno-ranker">
              <span>Similarity</span>
              <h2>Compare phenotypes</h2>
              <p>Run sample-level Pheno-Ranker comparisons with heatmap, MDS, and graph views.</p>
            </Link>
            <Link className={styles.card} to="/docs/admin-guide/model-providers">
              <span>Administration</span>
              <h2>Configure models</h2>
              <p>Register approved OpenAI-compatible providers and expose safe user selection.</p>
            </Link>
          </div>
        </section>
      </main>
    </Layout>
  );
}
