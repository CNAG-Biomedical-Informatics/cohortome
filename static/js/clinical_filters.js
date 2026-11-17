// DOM-free value validation and labels shared by the React clinical editor and tests.
export const clinicalOperators = {
  eq: 'is', ne: 'is not', in: 'is any of', contains: 'contains',
  lt: 'less than', lte: 'at most', gt: 'greater than', gte: 'at least',
  between: 'between', is_present: 'is recorded', is_missing: 'is not recorded',
};
export const clinicalNoValue = operator => ['is_present', 'is_missing'].includes(operator);

export function parseClinicalFilterValues(kind, operator, inputs) {
  if (clinicalNoValue(operator)) return [];
  const values = inputs.map(raw => {
    const text = String(raw).trim();
    if (!text) throw new Error('Enter a value.');
    if (kind === 'number') {
      const value = Number(text);
      if (!Number.isFinite(value)) throw new Error('Enter a finite number.');
      return value;
    }
    if (kind === 'boolean') {
      if (!['true', 'false'].includes(text)) throw new Error('Choose Yes or No.');
      return text === 'true';
    }
    if (kind === 'date') {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || !Number.isFinite(Date.parse(text))
          || new Date(text).toISOString().slice(0, 10) !== text) throw new Error('Enter a valid date.');
    }
    return text;
  });
  const required = operator === 'between' ? 2 : 1;
  if (values.length < required) throw new Error(operator === 'between' ? 'Enter both range limits.' : 'Enter a value.');
  if (operator === 'between' && values[0] > values[1]) throw new Error('The lower limit must not exceed the upper limit.');
  if (values.length > 50) throw new Error('Use at most 50 values.');
  return operator === 'in' ? [...new Set(values)] : values;
}

export function clinicalRuleLabel(rule, field) {
  const display = value => typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value);
  const value = rule.values.map(display).join(rule.operator === 'between' ? ' and ' : ' or ');
  return `${field.label} ${clinicalOperators[rule.operator] || rule.operator}${value ? ' ' + value : ''}${value && field.unit ? ' ' + field.unit : ''}`;
}
