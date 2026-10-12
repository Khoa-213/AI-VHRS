/** First tab stop: jumps over the navigation to the page content. */
export default function SkipLink({ target = 'main' }: { target?: string }) {
  return <a href={`#${target}`} className="skip-link">Skip to content</a>
}
