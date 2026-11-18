export function patientScopeLabel(count, total = null) {
  return `${count.toLocaleString()}${total !== null ? ` of ${total.toLocaleString()}` : ''} patients in scope`;
}
