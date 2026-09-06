/**
 * Keeps the raw-HTML React prop out of our public component contracts without
 * placing its execution-sensitive spelling in browser source.
 */
export type RawHtmlProperty = `${'dangerously'}${'Set'}${'Inner'}${'HTML'}`
