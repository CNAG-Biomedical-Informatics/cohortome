import React from 'react';
import { EvidenceResults } from './analysis-results/evidence.jsx';
import { ExpressionResults } from './analysis-results/expression.jsx';
import { MethylationResults } from './analysis-results/methylation.jsx';
import { QuantitativeResults } from './analysis-results/quantitative.jsx';
import { PathwayResults } from './analysis-results/pathway.jsx';
import { WorkflowResults } from './analysis-results/workflow.jsx';

export function ScientificResults({ model, turnIndex }) {
  if (!model) return null;
  if (model.kind === 'evidence') return <EvidenceResults model={model} turnIndex={turnIndex} />;
  if (model.kind === 'expression') return <ExpressionResults model={model} turnIndex={turnIndex} />;
  if (model.kind === 'qc' || model.kind === 'methylation')
    return <MethylationResults model={model} turnIndex={turnIndex} />;
  if (model.kind === 'quantitative')
    return <QuantitativeResults model={model} turnIndex={turnIndex} />;
  if (model.kind === 'pathway') return <PathwayResults model={model} turnIndex={turnIndex} />;
  if (model.kind === 'workflow') return <WorkflowResults model={model} turnIndex={turnIndex} />;
  return null;
}
