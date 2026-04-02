import type {ReactNode} from 'react';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  eyebrow: string;
  title: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    eyebrow: 'Workspace model',
    title: 'One active workspace, multiple datasets when needed',
    description: (
      <>
        Patient Navigator uses the concept of a workspace for the currently
        loaded dataset scope. A workspace may contain one dataset or multiple
        authorized datasets.
      </>
    ),
  },
  {
    eyebrow: 'Cross-tab flow',
    title: 'Build subsets in Query, interpret them in Analysis',
    description: (
      <>
        The app is designed around handoffs: browse in Dashboard, narrow in
        Query, interpret in Analysis, and switch to Pheno-Ranker when you need
        sample-level phenotypic similarity.
      </>
    ),
  },
  {
    eyebrow: 'Access control',
    title: 'Datasets are governed by visibility, groups, and direct users',
    description: (
      <>
        Dataset access is controlled at the dataset layer. Groups are the
        default access path, while direct user assignment exists for exceptions
        such as groupless users or temporary access.
      </>
    ),
  },
];

function Feature({eyebrow, title, description}: FeatureItem) {
  return (
    <article className={styles.featureCard}>
      <div className={styles.featureEyebrow}>{eyebrow}</div>
      <Heading as="h3" className={styles.featureTitle}>
        {title}
      </Heading>
      <p className={styles.featureDescription}>{description}</p>
    </article>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.featureGrid}>
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
