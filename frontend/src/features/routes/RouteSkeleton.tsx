/** Placeholder route cards while an evaluation runs; the status banner carries the announcement. */
function RouteSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="grid gap-3" aria-hidden="true" data-testid="route-skeleton">
      <div className="skeleton h-5 w-28" />
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="grid gap-3 rounded-xl border border-white/10 bg-navy-800 p-4">
          <div className="flex items-center gap-2">
            <div className="skeleton h-1 w-6" />
            <div className="skeleton h-4 w-20" />
            <div className="skeleton ml-auto h-4 w-16 rounded-full" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            {Array.from({ length: 6 }, (_, j) => (
              <div key={j} className="grid gap-1.5">
                <div className="skeleton h-2.5 w-12" />
                <div className="skeleton h-4 w-16" />
              </div>
            ))}
          </div>
          <div className="skeleton h-2 w-full rounded-full" />
        </div>
      ))}
    </div>
  )
}

export default RouteSkeleton
