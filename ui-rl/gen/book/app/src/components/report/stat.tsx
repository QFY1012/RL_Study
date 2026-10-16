import * as React from "react"

import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { place, type Placed } from "./grid"

type StatProps = Placed & {
  label?: string
  value: React.ReactNode
  unit?: string
  size?: "lg" | "xl"
  // the number comes first, so a row of figures can align on their baselines
  captionBelow?: boolean
  quiet?: boolean
  delta?: string
  note?: string
  direction?: "up" | "down"
}

// A key figure: the number is set on a two-line (48px) line whatever its size,
// and the label and note are one line each, with nothing between them, so a row
// of figures stays on the lines and their tops line up.
function Stat({ label, value, unit, size, captionBelow, quiet, delta, note, direction, span, start, rowSpan, rowStart, className }: StatProps) {
  return (
    <div data-slot="custom-stat" className={cn("flex flex-col", place({ span, start, rowSpan, rowStart }), className)}>
      {label && !captionBelow && <span className="text-sm leading-6 text-muted-foreground">{label}</span>}
      <div className="flex h-12 items-baseline gap-2">
        <span className={cn("font-light leading-12 tabular-nums", size === "lg" ? "text-5xl" : size === "xl" ? "text-[44px]" : "text-3xl")}>{value}</span>
        {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
      </div>
      {label && captionBelow && <span className={quiet ? "text-xs leading-6 text-muted-foreground" : "text-sm leading-6"}>{label}</span>}
      {(delta || note) && (
        <div className="flex h-6 items-center gap-2">
          {delta && (
            <Badge variant="outline" className={direction === "down" ? "text-destructive" : undefined}>
              {delta}
            </Badge>
          )}
          {/* without a delta badge the note carries the change, so a fall is drawn in the destructive colour */}
          {note && <span className={cn("text-xs leading-6", !delta && direction === "down" ? "text-destructive" : "text-muted-foreground")}>{note}</span>}
        </div>
      )}
    </div>
  )
}

export { Stat }
