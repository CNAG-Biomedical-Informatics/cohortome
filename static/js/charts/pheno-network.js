// Chart-only module. Controllers retain requests, chat state and run execution.
export function createPhenoNetworkChart({
  renderPhenoCohortLegend,
  getEffectivePhenoCohortMetric,
  getPhenoMdsCohortInfo,
  displayIdentity,
  state,
  normalizePhenoSelectedRecordIds,
  escapeHtml,
}) {
  async function renderInteractivePhenoGraph(file, runOptions = {}) {
    const plotEl = document.getElementById('phenoGraphPlot');
    const noteEl = document.getElementById('phenoGraphSelectionNote');
    const thresholdEl = document.getElementById('phenoGraphThreshold');
    const thresholdLabelEl = document.getElementById('phenoGraphThresholdLabel');
    const thresholdMetaEl = document.getElementById('phenoGraphThresholdMeta');
    const topKEl = document.getElementById('phenoGraphTopK');
    const edgeLabelsEl = document.getElementById('phenoGraphEdgeLabels');
    const largestComponentEl = document.getElementById('phenoGraphLargestComponent');
    if (!plotEl) {
      return;
    }
    if (typeof window.cytoscape === 'undefined') {
      plotEl.innerHTML =
        '<div class="empty">Interactive Cytoscape view is unavailable in this browser.</div>';
      return;
    }
    if (plotEl._cy && typeof plotEl._cy.destroy === 'function') {
      plotEl._cy.destroy();
      plotEl._cy = null;
    }
    try {
      const response = await fetch(file.url);
      if (!response.ok) {
        plotEl.innerHTML = '<div class="empty">Unable to load the cohort graph.</div>';
        return;
      }
      const payload = await response.json();
      const elements =
        payload &&
        typeof payload === 'object' &&
        payload.elements &&
        typeof payload.elements === 'object'
          ? payload.elements
          : {};
      const rawNodes = Array.isArray(elements.nodes) ? elements.nodes : [];
      const rawEdges = Array.isArray(elements.edges) ? elements.edges : [];
      if (!rawNodes.length) {
        plotEl.innerHTML = '<div class="empty">No graph nodes were produced for this run.</div>';
        return;
      }
      const nodeIds = rawNodes
        .map((node) => String(node && node.data && node.data.id ? node.data.id : '').trim())
        .filter(Boolean);
      renderPhenoCohortLegend('phenoGraphCohortLegend', nodeIds);
      const similarityMetric = getEffectivePhenoCohortMetric();
      const strongerIsHigher = similarityMetric !== 'hamming';
      const metricLabel = strongerIsHigher ? 'Jaccard similarity' : 'Hamming dissimilarity';
      const defaultTopKNeighbors = nodeIds.length > 80 ? 1 : nodeIds.length > 36 ? 2 : 3;
      const normalizedNodes = rawNodes.map((node) => {
        const id = String(node && node.data && node.data.id ? node.data.id : '').trim();
        const cohort = getPhenoMdsCohortInfo(id);
        return {
          data: {
            ...(node && node.data ? node.data : {}),
            id,
            label: displayIdentity(id),
            cohort_label: cohort.label,
            cohort_color: cohort.color,
          },
        };
      });
      const graphMinWeight = Number(
        runOptions &&
          runOptions.graph_min_weight !== undefined &&
          runOptions.graph_min_weight !== null
          ? runOptions.graph_min_weight
          : NaN,
      );
      const graphMaxWeight = Number(
        runOptions &&
          runOptions.graph_max_weight !== undefined &&
          runOptions.graph_max_weight !== null
          ? runOptions.graph_max_weight
          : NaN,
      );
      const hasGraphMinWeight = Number.isFinite(graphMinWeight);
      const hasGraphMaxWeight = Number.isFinite(graphMaxWeight);
      const normalizedEdges = rawEdges
        .map((edge) => {
          const source = String(
            edge && edge.data && edge.data.source ? edge.data.source : '',
          ).trim();
          const target = String(
            edge && edge.data && edge.data.target ? edge.data.target : '',
          ).trim();
          const weightValue = Number(
            edge && edge.data && edge.data.weight ? edge.data.weight : NaN,
          );
          const weight = Number.isFinite(weightValue) ? weightValue : 0;
          return {
            data: {
              ...(edge && edge.data ? edge.data : {}),
              source,
              target,
              weight,
            },
          };
        })
        .filter((edge) => {
          const weight = Number(edge && edge.data ? edge.data.weight : NaN);
          if (!Number.isFinite(weight)) {
            return false;
          }
          if (hasGraphMinWeight && weight < graphMinWeight) {
            return false;
          }
          if (hasGraphMaxWeight && weight > graphMaxWeight) {
            return false;
          }
          return true;
        });
      const edgeLookup = new Map();
      normalizedEdges.forEach((edge) => {
        const source = String(edge.data.source || '').trim();
        const target = String(edge.data.target || '').trim();
        if (!source || !target) {
          return;
        }
        const key = [source, target].sort().join('\u0000');
        edgeLookup.set(key, Number(edge.data.weight));
      });
      const uniqueSortedWeights = Array.from(
        new Set(
          normalizedEdges
            .map((edge) => Number(edge.data.weight))
            .filter((weight) => Number.isFinite(weight)),
        ),
      ).sort((a, b) => (strongerIsHigher ? b - a : a - b));
      const preferredEdgeBudget = Math.max(36, Math.min(140, Math.round(nodeIds.length * 1.5)));
      let defaultStrengthIndex = 0;
      if (uniqueSortedWeights.length) {
        if (strongerIsHigher) {
          defaultStrengthIndex = Math.max(
            0,
            Math.min(uniqueSortedWeights.length - 1, preferredEdgeBudget - 1),
          );
        } else {
          const firstWeightAtOrAboveTwoIndex = uniqueSortedWeights.findIndex(
            (weight) => weight >= 2,
          );
          defaultStrengthIndex =
            firstWeightAtOrAboveTwoIndex <= 0 ? 0 : firstWeightAtOrAboveTwoIndex - 1;
          if (firstWeightAtOrAboveTwoIndex === -1) {
            defaultStrengthIndex = uniqueSortedWeights.length - 1;
          }
        }
      }
      const thresholdState = {
        cy: null,
        thresholdValue: uniqueSortedWeights[defaultStrengthIndex] ?? null,
      };

      const computeLargestComponentNodeIds = (nodes, edges) => {
        const adjacency = new Map();
        nodes.forEach((node) => {
          const id = String(node && node.data && node.data.id ? node.data.id : '').trim();
          if (id && !adjacency.has(id)) {
            adjacency.set(id, new Set());
          }
        });
        edges.forEach((edge) => {
          const source = String(
            edge && edge.data && edge.data.source ? edge.data.source : '',
          ).trim();
          const target = String(
            edge && edge.data && edge.data.target ? edge.data.target : '',
          ).trim();
          if (!source || !target) {
            return;
          }
          if (!adjacency.has(source)) {
            adjacency.set(source, new Set());
          }
          if (!adjacency.has(target)) {
            adjacency.set(target, new Set());
          }
          adjacency.get(source).add(target);
          adjacency.get(target).add(source);
        });
        const visited = new Set();
        let largest = [];
        adjacency.forEach((_neighbors, nodeId) => {
          if (visited.has(nodeId)) {
            return;
          }
          const queue = [nodeId];
          const component = [];
          visited.add(nodeId);
          while (queue.length) {
            const current = queue.shift();
            component.push(current);
            const neighbors = adjacency.get(current) || new Set();
            neighbors.forEach((neighbor) => {
              if (!visited.has(neighbor)) {
                visited.add(neighbor);
                queue.push(neighbor);
              }
            });
          }
          if (component.length > largest.length) {
            largest = component;
          }
        });
        return new Set(largest);
      };

      const qualifiesEdge = (edge, thresholdValue) => {
        const weight = Number(edge && edge.data ? edge.data.weight : NaN);
        if (!Number.isFinite(weight)) {
          return false;
        }
        if (thresholdValue === null || thresholdValue === undefined) {
          return true;
        }
        return strongerIsHigher ? weight >= thresholdValue : weight <= thresholdValue;
      };

      const buildEdgeVisual = (weight) => {
        const numericWeight = Number(weight);
        const finiteWeights = uniqueSortedWeights
          .filter((value) => Number.isFinite(Number(value)))
          .map((value) => Number(value));
        const minWeight = finiteWeights.length ? Math.min(...finiteWeights) : numericWeight;
        const maxWeight = finiteWeights.length ? Math.max(...finiteWeights) : numericWeight;
        let normalizedStrength = 0.7;
        if (
          Number.isFinite(numericWeight) &&
          Number.isFinite(minWeight) &&
          Number.isFinite(maxWeight) &&
          maxWeight !== minWeight
        ) {
          normalizedStrength = strongerIsHigher
            ? (numericWeight - minWeight) / (maxWeight - minWeight)
            : (maxWeight - numericWeight) / (maxWeight - minWeight);
        }
        normalizedStrength = Math.max(0, Math.min(1, normalizedStrength));
        const perfectMatch = strongerIsHigher
          ? Math.abs(numericWeight - 1) < 0.000001
          : Math.abs(numericWeight) < 0.000001;
        return {
          width: 1 + normalizedStrength * 8,
          opacity: 0.22 + normalizedStrength * 0.72,
          color: perfectMatch ? '#020617' : '#94a3b8',
        };
      };
      const formatGraphWeight = (weight) => {
        const numericWeight = Number(weight);
        if (!Number.isFinite(numericWeight)) {
          return 'n/a';
        }
        return strongerIsHigher ? numericWeight.toFixed(3) : String(Math.round(numericWeight));
      };
      const describeGraphEdge = (edge) => {
        const source = String(edge && edge.data ? edge.data('source') || '' : '').trim();
        const target = String(edge && edge.data ? edge.data('target') || '' : '').trim();
        const weight = Number(edge && edge.data ? edge.data('weight') : NaN);
        if (!source || !target || !Number.isFinite(weight)) {
          return 'Selected edge has no available weight.';
        }
        return `Selected edge ${source} to ${target}. ${metricLabel} = ${formatGraphWeight(weight)}.`;
      };
      const currentEdgeLabelMode = () => {
        const mode = String(edgeLabelsEl && edgeLabelsEl.value ? edgeLabelsEl.value : 'selected')
          .trim()
          .toLowerCase();
        return ['off', 'selected', 'visible'].includes(mode) ? mode : 'selected';
      };
      const syncEdgeLabels = (cy) => {
        const mode = currentEdgeLabelMode();
        cy.edges().forEach((edge) => {
          const shouldShow = mode === 'visible' || (mode === 'selected' && edge.selected());
          edge.data('value_label', shouldShow ? formatGraphWeight(edge.data('weight')) : '');
        });
      };

      const syncSelectedNodes = (cy) => {
        const selectedNodes = cy.$('node:selected').toArray();
        const rawSelectedNodeIds = selectedNodes
          .map((node) => String(node.id() || '').trim())
          .filter(Boolean);
        state.selectedGraphRecordIds = normalizePhenoSelectedRecordIds(rawSelectedNodeIds);
        if (noteEl) {
          if (rawSelectedNodeIds.length === 2) {
            const [leftId, rightId] = rawSelectedNodeIds;
            const visibleEdge = selectedNodes[0].edgesWith(selectedNodes[1]).toArray()[0] || null;
            const visibleWeight = visibleEdge ? Number(visibleEdge.data('weight')) : NaN;
            const edgeKey = [leftId, rightId].sort().join('\u0000');
            const value = Number.isFinite(visibleWeight) ? visibleWeight : edgeLookup.get(edgeKey);
            if (Number.isFinite(value)) {
              noteEl.textContent = `Selected ${leftId} and ${rightId}. ${metricLabel} = ${Number(value).toFixed(3)}.`;
            } else {
              noteEl.textContent = `Selected ${leftId} and ${rightId}. No direct edge is currently available for this pair.`;
            }
          } else if (rawSelectedNodeIds.length) {
            noteEl.textContent = `Selected ${rawSelectedNodeIds.length} graph nodes.`;
          } else {
            noteEl.textContent =
              'Click an edge to inspect its value. Click or box-select graph nodes to reuse them in Analysis or save them as a cohort.';
          }
        }
      };

      const renderThresholdMeta = (edgeCount, thresholdValue) => {
        if (!thresholdLabelEl || !thresholdMetaEl) {
          return;
        }
        if (!Number.isFinite(thresholdValue)) {
          thresholdLabelEl.textContent = 'Displayed edges';
          thresholdMetaEl.textContent = `${edgeCount} strongest edges shown.`;
          return;
        }
        const formatted = Number(thresholdValue).toFixed(3);
        if (strongerIsHigher) {
          thresholdLabelEl.textContent = 'Minimum similarity';
          thresholdMetaEl.textContent = `${edgeCount} of ${normalizedEdges.length} edges shown at similarity >= ${formatted}.`;
        } else {
          thresholdLabelEl.textContent = 'Maximum dissimilarity';
          thresholdMetaEl.textContent = `${edgeCount} of ${normalizedEdges.length} edges shown at dissimilarity <= ${formatted}.`;
        }
        const bounds = [];
        if (hasGraphMinWeight) {
          bounds.push(`min ${graphMinWeight.toFixed(3)}`);
        }
        if (hasGraphMaxWeight) {
          bounds.push(`max ${graphMaxWeight.toFixed(3)}`);
        }
        if (bounds.length) {
          thresholdMetaEl.textContent += ` Export cutoff: ${bounds.join(', ')}.`;
        }
      };

      const drawGraph = (thresholdValue) => {
        if (thresholdState.cy && typeof thresholdState.cy.destroy === 'function') {
          thresholdState.cy.destroy();
        }
        const thresholdFilteredEdges = normalizedEdges.filter((edge) =>
          qualifiesEdge(edge, thresholdValue),
        );
        const incidentByNode = new Map();
        thresholdFilteredEdges.forEach((edge, index) => {
          const source = String(edge.data.source || '').trim();
          const target = String(edge.data.target || '').trim();
          if (!source || !target) {
            return;
          }
          if (!incidentByNode.has(source)) {
            incidentByNode.set(source, []);
          }
          if (!incidentByNode.has(target)) {
            incidentByNode.set(target, []);
          }
          incidentByNode.get(source).push({ edge, index });
          incidentByNode.get(target).push({ edge, index });
        });
        const currentTopK = Math.max(
          1,
          Number(topKEl && topKEl.value ? topKEl.value : defaultTopKNeighbors),
        );
        const retainedEdgeIndexes = new Set();
        incidentByNode.forEach((items) => {
          items
            .slice()
            .sort((left, right) => {
              const leftWeight = Number(left.edge.data.weight);
              const rightWeight = Number(right.edge.data.weight);
              return strongerIsHigher ? rightWeight - leftWeight : leftWeight - rightWeight;
            })
            .slice(0, currentTopK)
            .forEach((item) => retainedEdgeIndexes.add(item.index));
        });
        let filteredEdges = thresholdFilteredEdges
          .filter((_edge, index) => retainedEdgeIndexes.has(index))
          .map((edge) => {
            const visual = buildEdgeVisual(edge.data.weight);
            return {
              data: {
                ...edge.data,
                width: visual.width,
                opacity: visual.opacity,
                color: visual.color,
                value_label: '',
              },
            };
          });
        const currentLargestComponentOnly = Boolean(
          largestComponentEl && largestComponentEl.checked,
        );
        if (currentLargestComponentOnly && filteredEdges.length) {
          const largestNodeIds = computeLargestComponentNodeIds(normalizedNodes, filteredEdges);
          filteredEdges = filteredEdges.filter((edge) => {
            const source = String(edge.data.source || '').trim();
            const target = String(edge.data.target || '').trim();
            return largestNodeIds.has(source) && largestNodeIds.has(target);
          });
        }
        const visibleNodeIds = new Set();
        filteredEdges.forEach((edge) => {
          visibleNodeIds.add(String(edge.data.source || '').trim());
          visibleNodeIds.add(String(edge.data.target || '').trim());
        });
        const filteredNodes = visibleNodeIds.size
          ? normalizedNodes.filter((node) => visibleNodeIds.has(String(node.data.id || '').trim()))
          : normalizedNodes;
        const cy = window.cytoscape({
          container: plotEl,
          elements: [...filteredNodes, ...filteredEdges],
          layout: {
            name: 'cose',
            animate: false,
            fit: true,
            padding: 28,
            nodeRepulsion: 5000,
            idealEdgeLength: 70,
            edgeElasticity: 80,
          },
          boxSelectionEnabled: true,
          selectionType: 'additive',
          style: [
            {
              selector: 'node',
              style: {
                'background-color': 'data(cohort_color)',
                label: 'data(label)',
                color: window.CohortomeTheme.colors().ink,
                'font-size': 10,
                'text-wrap': 'wrap',
                'text-max-width': 96,
                'text-valign': 'bottom',
                'text-halign': 'center',
                'text-margin-y': 8,
                'border-width': 1.5,
                'border-color': '#ffffff',
                width: 18,
                height: 18,
              },
            },
            {
              selector: 'edge',
              style: {
                width: 'data(width)',
                'line-color': 'data(color)',
                opacity: 'data(opacity)',
                'curve-style': 'bezier',
                label: 'data(value_label)',
                color: window.CohortomeTheme.colors().ink,
                'font-size': 9,
                'text-background-color': window.CohortomeTheme.colors().panel,
                'text-background-opacity': 0.86,
                'text-background-padding': 2,
                'text-rotation': 'autorotate',
                'text-margin-y': -4,
              },
            },
            {
              selector: 'edge:selected',
              style: {
                'line-color': '#0f766e',
                opacity: 0.92,
                'overlay-color': '#99f6e4',
                'overlay-opacity': 0.18,
              },
            },
            {
              selector: ':selected',
              style: {
                'border-color': '#991b1b',
                'border-width': 3,
                'overlay-color': '#fca5a5',
                'overlay-opacity': 0.12,
              },
            },
          ],
        });
        thresholdState.cy = cy;
        plotEl._cy = cy;
        cy.on('select unselect', 'node', () => syncSelectedNodes(cy));
        cy.on('tap', 'edge', (event) => {
          const edge = event && event.target ? event.target : null;
          if (edge && typeof edge.select === 'function') {
            cy.$('edge:selected').unselect();
            edge.select();
            syncEdgeLabels(cy);
          }
          if (noteEl) {
            noteEl.textContent = describeGraphEdge(edge);
          }
        });
        syncSelectedNodes(cy);
        syncEdgeLabels(cy);
        renderThresholdMeta(filteredEdges.length, thresholdValue);
        if (thresholdMetaEl) {
          const parts = [thresholdMetaEl.textContent];
          parts.push(
            currentTopK >= 9999
              ? 'Showing all neighbors per node.'
              : `Top ${currentTopK} neighbors per node.`,
          );
          if (currentLargestComponentOnly) {
            parts.push('Largest component only.');
          }
          thresholdMetaEl.textContent = parts.filter(Boolean).join(' ');
        }
      };

      if (thresholdEl && uniqueSortedWeights.length) {
        thresholdEl.min = '0';
        thresholdEl.max = String(uniqueSortedWeights.length - 1);
        thresholdEl.step = '1';
        thresholdEl.value = String(defaultStrengthIndex);
        thresholdEl.addEventListener('input', () => {
          const index = Math.max(
            0,
            Math.min(uniqueSortedWeights.length - 1, Number(thresholdEl.value || 0)),
          );
          thresholdState.thresholdValue = uniqueSortedWeights[index];
          drawGraph(thresholdState.thresholdValue);
        });
      } else if (thresholdEl) {
        thresholdEl.disabled = true;
      }
      if (topKEl) {
        topKEl.value = String(defaultTopKNeighbors);
        topKEl.addEventListener('change', () => {
          drawGraph(thresholdState.thresholdValue);
        });
      }
      if (edgeLabelsEl) {
        edgeLabelsEl.value = 'selected';
        edgeLabelsEl.addEventListener('change', () => {
          if (thresholdState.cy) {
            syncEdgeLabels(thresholdState.cy);
          }
        });
      }
      if (largestComponentEl) {
        largestComponentEl.checked = true;
        largestComponentEl.addEventListener('change', () => {
          drawGraph(thresholdState.thresholdValue);
        });
      }
      drawGraph(thresholdState.thresholdValue);
    } catch (error) {
      plotEl.innerHTML = `<div class="empty">${escapeHtml(error && error.message ? error.message : 'Unable to render the graph.')}</div>`;
    }
  }
  return { renderInteractivePhenoGraph };
}
