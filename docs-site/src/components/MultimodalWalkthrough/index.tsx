import React from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';

export default function MultimodalWalkthrough() {
  return (
    <figure style={{margin: '1.5rem 0'}}>
      <video
        controls
        playsInline
        preload="none"
        aria-label="Select clinical and proteomics data and save a patient cohort"
        poster={useBaseUrl('/media/multimodal-cohort-poster.jpg')}
        style={{display: 'block', width: '100%', borderRadius: 8}}
      >
        <source src={useBaseUrl('/media/multimodal-cohort.mp4')} type="video/mp4" />
        Your browser does not support embedded video.
      </video>
      <figcaption style={{marginTop: '0.5rem', fontSize: '0.9rem'}}>
        28-second silent walkthrough with synthetic demo data: select Clinical
        and Proteomics, save the eight matching patients, then find the saved
        group in Cohorts. Results illustrate the interface, not biological findings.
      </figcaption>
    </figure>
  );
}
