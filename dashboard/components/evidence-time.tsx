/** Fixed UTC formatting keeps server/client output aligned. The original evidence stays inspectable. */
export function EvidenceTime({ value }: { value: string }) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return <span>{value}</span>;
  const readable = new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium', timeStyle: 'medium', timeZone: 'UTC',
  }).format(date);
  return <time dateTime={value} title={value}>{readable} UTC</time>;
}
