import type {CSSProperties} from 'react';

import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';

import styles from './index.module.css';

const researchPaths = [
  {
    label: 'Explore',
    title: 'See each patient over time',
    body: 'Move between visits, diagnoses, treatments, assays, imaging, and the data available for each patient.',
    to: '/docs/user-guide/dashboard',
  },
  {
    label: 'Cohorts',
    title: 'Find and save patient groups',
    body: 'Ask questions to find groups of patients, save those groups, and carry them into analysis without losing context.',
    to: '/docs/user-guide/query',
  },
  {
    label: 'Analysis',
    title: 'Run methods and keep the result',
    body: 'Combine measurements, run reviewed methods, inspect plots, and keep the inputs and outputs together.',
    to: '/docs/user-guide/analysis',
  },
  {
    label: 'Set up',
    title: 'Decide who can use what',
    body: 'Choose who can use each dataset, what may be sent to a model, and where protected data are allowed to go.',
    to: '/docs/admin-guide/real-data-security',
  },
];

export default function Home() {
  const workspaceImage = useBaseUrl('/img/screenshots/workspace-shell.png');
  const journeyDiagram = useBaseUrl('/img/cohortome-research-journey.svg');
  const journeyDiagramMobile = useBaseUrl('/img/cohortome-research-journey-mobile.svg');
  const aiDiagram = useBaseUrl('/img/cohortome-governed-ai.svg');
  const aiDiagramMobile = useBaseUrl('/img/cohortome-governed-ai-mobile.svg');

  const heroStyle = {
    '--cohortome-workspace-image': `url("${workspaceImage}")`,
  } as CSSProperties;

  return (
    <Layout
      title="COHORTome"
      description="Open-source workspace for connecting longitudinal clinical records and multimodal assays, finding cohorts, and running traceable analyses.">
      <main className={styles.page}>
        <section className={styles.hero} style={heroStyle}>
          <div className={styles.heroContent}>
            <p className={styles.eyebrow}>Open-source biomedical research workspace</p>
            <h1 className={styles.heroWordmark} aria-label="COHORTome">
              <span className={styles.heroWordmarkPrimary}>COHORT</span>
              <span className={styles.heroWordmarkSecondary}>ome</span>
            </h1>
            <p className={styles.heroLead}>
              Bring clinical records, assays, and imaging together. Follow
              patients over time, find cohorts, and run analyses without losing
              where the data and results came from.
            </p>
            <div className={styles.heroActions}>
              <Link className="button button--primary button--lg" to="/docs/overview">
                See what COHORTome does
              </Link>
              <Link className="button button--outline button--secondary button--lg" to="/docs/admin-guide/local-auth-and-groups">
                Run from source
              </Link>
            </div>
            <div className={styles.heroSignals} aria-label="What COHORTome covers">
              <span>Patients over time</span>
              <span>Clinical + assay data</span>
              <span>Optional language models</span>
              <span>Saved runs and results</span>
            </div>
          </div>
        </section>

        <section className={styles.definitionBand}>
          <div className={styles.inner}>
            <p className={styles.sectionLabel}>Why it exists</p>
            <div className={styles.definitionGrid}>
              <h2>Stored data are not yet usable research data.</h2>
              <p>
                COHORTome can be deployed alongside an existing warehouse, file service,
                or institutional data system. It receives authorized data and turns
                them into a workspace where researchers can connect clinical and
                assay information, define cohorts, and run traceable analyses. The
                source systems continue to store and distribute the original data.
              </p>
            </div>
          </div>
        </section>

        <section className={styles.architectureSection}>
          <div className={styles.inner}>
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.sectionLabel}>A research journey</p>
                <h2>Keep every step connected</h2>
              </div>
              <p>
                COHORTome links the records that belong to the same patient, sample,
                and visit. A research question can then move into cohort discovery
                and analysis without losing its authorized data scope or history.
              </p>
            </div>
            <figure className={styles.diagramFigure}>
              <picture>
                <source media="(max-width: 700px)" srcSet={journeyDiagramMobile} />
                <img
                  src={journeyDiagram}
                  alt="Approved clinical, assay, and imaging data enter COHORTome, where patient records are linked, a cohort is found, and a reviewed analysis is saved with its history."
                  loading="eager"
                />
              </picture>
            </figure>
          </div>
        </section>

        <section className={styles.pathsSection}>
          <div className={styles.inner}>
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.sectionLabel}>What you can do</p>
                <h2>Move from a question to a result</h2>
              </div>
              <p>
                The workspace keeps the selected people, permitted datasets,
                analysis state, and generated results connected as researchers move
                between tasks.
              </p>
            </div>
            <div className={styles.pathGrid}>
              {researchPaths.map((path) => (
                <Link className={styles.pathCard} key={path.label} to={path.to}>
                  <span>{path.label}</span>
                  <h3>{path.title}</h3>
                  <p>{path.body}</p>
                  <strong>Learn more</strong>
                </Link>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.aiSection}>
          <div className={styles.inner}>
            <div className={styles.aiIntro}>
              <div>
                <p className={styles.sectionLabel}>Language models</p>
                <h2>AI can help. COHORTome stays in control.</h2>
              </div>
              <div>
                <p>
                  COHORTome answers familiar questions directly and can use an approved
                  language model for more flexible requests. Before anything is sent
                  to a model, COHORTome checks what the user and dataset allow. COHORTome, not the
                  model, remains responsible for running the operation.
                </p>
                <Link to="/docs/concepts/governed-ai">How model access works</Link>
              </div>
            </div>
            <figure className={styles.aiFigure}>
              <picture>
                <source media="(max-width: 700px)" srcSet={aiDiagramMobile} />
                <img
                  src={aiDiagram}
                  alt="COHORTome checks access, works with or without an approved language model, runs the operation, and keeps the result with its history."
                  loading="lazy"
                />
              </picture>
            </figure>
          </div>
        </section>

        <section className={styles.contextSection}>
          <div className={styles.inner}>
            <div className={styles.contextGrid}>
              <div>
                <p className={styles.sectionLabel}>First deployment</p>
                <h2>A generic tool, first deployed for 3TR</h2>
                <p>
                  COHORTome is not tied to 3TR or to one disease area. Its first
                  consortium-scale deployment will be for 3TR. PRECISESADS data,
                  held in the 3TR Omics DM Warehouse and used with FPS collaborators
                  in Granada, provide the first real dataset use case. The same
                  software can be deployed for other approved biomedical datasets.
                </p>
              </div>
              <div className={styles.contextLinks}>
                <Link to="/docs/project/3tr-and-precisesads">
                  3TR and PRECISESADS context
                </Link>
                <Link to="/docs/project/scope-and-boundaries">
                  Scope and non-goals
                </Link>
                <Link to="/docs/validation/evaluation-and-evidence">
                  Evaluation and evidence plan
                </Link>
                <Link to="/docs/about/citation-and-funding">
                  Citation, funding, and attribution
                </Link>
              </div>
            </div>
            <div className={styles.openSourceNote}>
              <div>
                <strong>Open source under Apache-2.0</strong>
                <span>Run it independently, inspect how it works, and contribute changes.</span>
              </div>
              <Link to="https://github.com/mrueda/cohortome">
                View the source on GitHub
              </Link>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
