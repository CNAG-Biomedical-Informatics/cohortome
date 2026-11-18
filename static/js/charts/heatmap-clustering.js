// Chart-only module. Controllers retain requests, chat state and run execution.
function euclideanDistance(valuesA, valuesB) {
  let total = 0;
  for (let index = 0; index < valuesA.length; index += 1) {
    const delta = Number(valuesA[index] || 0) - Number(valuesB[index] || 0);
    total += delta * delta;
  }
  return Math.sqrt(total);
}

function clusterDistance(leftCluster, rightCluster, pairwiseDistances) {
  let maxDistance = 0;
  leftCluster.members.forEach((leftMember) => {
    rightCluster.members.forEach((rightMember) => {
      const key =
        leftMember < rightMember ? `${leftMember}:${rightMember}` : `${rightMember}:${leftMember}`;
      maxDistance = Math.max(maxDistance, Number(pairwiseDistances.get(key) || 0));
    });
  });
  return maxDistance;
}

export function buildHeatmapRowCluster(matrixRows, sampleNames) {
  if (
    !Array.isArray(matrixRows) ||
    matrixRows.length < 2 ||
    !Array.isArray(sampleNames) ||
    !sampleNames.length
  ) {
    return null;
  }
  const pairwiseDistances = new Map();
  matrixRows.forEach((row, index) => {
    const leftValues = sampleNames.map((sample) => Number(row[sample] || 0));
    for (let rightIndex = index + 1; rightIndex < matrixRows.length; rightIndex += 1) {
      const rightValues = sampleNames.map((sample) => Number(matrixRows[rightIndex][sample] || 0));
      pairwiseDistances.set(`${index}:${rightIndex}`, euclideanDistance(leftValues, rightValues));
    }
  });
  let nextClusterId = matrixRows.length;
  let clusters = matrixRows.map((row, index) => ({
    id: index,
    members: [index],
    height: 0,
    left: null,
    right: null,
    label: String(row.gene_id || `Gene ${index + 1}`),
  }));
  while (clusters.length > 1) {
    let bestPair = null;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let leftIndex = 0; leftIndex < clusters.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < clusters.length; rightIndex += 1) {
        const distance = clusterDistance(
          clusters[leftIndex],
          clusters[rightIndex],
          pairwiseDistances,
        );
        if (distance < bestDistance) {
          bestDistance = distance;
          bestPair = [leftIndex, rightIndex];
        }
      }
    }
    if (!bestPair) break;
    const [leftIndex, rightIndex] = bestPair;
    const leftCluster = clusters[leftIndex];
    const rightCluster = clusters[rightIndex];
    const mergedCluster = {
      id: nextClusterId,
      members: leftCluster.members.concat(rightCluster.members),
      height: bestDistance,
      left: leftCluster,
      right: rightCluster,
      label: '',
    };
    nextClusterId += 1;
    clusters = clusters.filter((_, index) => index !== leftIndex && index !== rightIndex);
    clusters.push(mergedCluster);
  }
  return clusters[0] || null;
}

export function flattenHeatmapClusterOrder(node) {
  if (!node) return [];
  if (!node.left && !node.right) return [node.members[0]];
  return flattenHeatmapClusterOrder(node.left).concat(flattenHeatmapClusterOrder(node.right));
}

export function buildHeatmapClusterTreeFromR(payload) {
  const labels = Array.isArray(payload && payload.labels)
    ? payload.labels.map((item) => String(item || ''))
    : [];
  const merge = Array.isArray(payload && payload.merge) ? payload.merge : [];
  const heights = Array.isArray(payload && payload.height) ? payload.height : [];
  if (!labels.length || !merge.length || merge.length !== heights.length) return null;
  const leafNodes = new Map();
  labels.forEach((label, index) => {
    leafNodes.set(index + 1, {
      id: -(index + 1),
      members: [index],
      height: 0,
      left: null,
      right: null,
      label,
    });
  });
  const clusterNodes = new Map();
  for (let index = 0; index < merge.length; index += 1) {
    const pair = Array.isArray(merge[index]) ? merge[index] : [];
    if (pair.length !== 2) return null;
    const resolveNode = (value) => {
      if (value < 0) return leafNodes.get(Math.abs(value)) || null;
      return clusterNodes.get(value) || null;
    };
    const left = resolveNode(Number(pair[0]));
    const right = resolveNode(Number(pair[1]));
    if (!left || !right) return null;
    clusterNodes.set(index + 1, {
      id: index + 1,
      members: left.members.concat(right.members),
      height: Number(heights[index] || 0),
      left,
      right,
      label: '',
    });
  }
  return clusterNodes.get(merge.length) || null;
}

export function buildHeatmapDendrogramSvg(clusterRoot, orderedRows) {
  if (!clusterRoot || !Array.isArray(orderedRows) || orderedRows.length < 2) return '';
  const width = 140;
  const height = 520;
  const paddingTop = 32;
  const paddingBottom = 120;
  const usableHeight = Math.max(height - paddingTop - paddingBottom, 80);
  const rowHeight = usableHeight / orderedRows.length;
  const leafY = new Map();
  orderedRows.forEach((row, index) => {
    leafY.set(String(row.gene_id || ''), paddingTop + index * rowHeight + rowHeight / 2);
  });
  const maxHeight = Math.max(Number(clusterRoot.height || 0), 1);
  const lines = [];

  function renderNode(node) {
    if (!node.left && !node.right) {
      return {
        x: width,
        y: leafY.get(String(node.label || '')) || paddingTop,
      };
    }
    const left = renderNode(node.left);
    const right = renderNode(node.right);
    const x = width - (Number(node.height || 0) / maxHeight) * (width - 12);
    lines.push(
      `<line x1="${x.toFixed(2)}" y1="${left.y.toFixed(2)}" x2="${left.x.toFixed(2)}" y2="${left.y.toFixed(2)}"></line>`,
    );
    lines.push(
      `<line x1="${x.toFixed(2)}" y1="${right.y.toFixed(2)}" x2="${right.x.toFixed(2)}" y2="${right.y.toFixed(2)}"></line>`,
    );
    lines.push(
      `<line x1="${x.toFixed(2)}" y1="${left.y.toFixed(2)}" x2="${x.toFixed(2)}" y2="${right.y.toFixed(2)}"></line>`,
    );
    return { x, y: (left.y + right.y) / 2 };
  }

  renderNode(clusterRoot);
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Heatmap row dendrogram"><g class="analysis-heatmap-dendrogram-lines">${lines.join('')}</g></svg>`;
}
