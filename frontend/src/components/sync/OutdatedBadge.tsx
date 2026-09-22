export function OutdatedBadge({ isOutdated }: { isOutdated: boolean }) {
  if (!isOutdated) {
    return <span className="badge badge-uptodate">Up to date</span>;
  }
  return (
    <span className="badge badge-outdated" role="status">
      Changes available
    </span>
  );
}
