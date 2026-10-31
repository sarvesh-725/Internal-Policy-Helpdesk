export default function CitationDrawer({ citations, onClose }) {
  return (
    <aside className="citation-drawer" aria-label="Policy sources">
      <div className="row"><h2>Policy sources</h2><button onClick={onClose}>Close</button></div>
      {citations.length === 0 ? <p>No policy citations are available for this response.</p> : citations.map((citation) => (
        <article className="citation" key={`${citation.document_id}-${citation.version}-${citation.section_id}`}>
          <strong>{citation.title}</strong>
          <small>{citation.document_id} · v{citation.version} · {citation.section_id}</small>
          <p>{citation.excerpt}</p>
        </article>
      ))}
    </aside>
  );
}
