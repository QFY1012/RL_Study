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

// A key figure. In a row of figures every Stat sits on the row's baseline, so a
// large figure and the smaller ones beside it share one baseline instead of
// lining up at the top (the page code does not have to ask for it). The figure's
// box and the unit's are trimmed to their baseline, so the row of figure and unit
// ends exactly on the baseline: the caption starts the same distance below it
// whatever the figure's size and whether or not there is a unit, and the
// captions of a row line up too.
function Stat({ label, value, unit, size, captionBelow, quiet, delta, note, direction, span, start, rowSpan, rowStart, className }: StatProps) {
  return (
    <div data-slot="custom-stat" className={cn(cn("flex flex-col self-baseline", captionBelow ? "gap-0" : "gap-2"), place({ span, start, rowSpan, rowStart }), className)}>
      {label && !captionBelow && <span className="text-sm leading-6 text-muted-foreground">{label}</span>}
      <div className="flex items-baseline gap-2 pb-2">
        <span className={cn("inline-block leading-none font-light tabular-nums [text-box:trim-both_cap_alphabetic]", size === "lg" ? "text-5xl" : size === "xl" ? "text-[44px]" : "text-3xl")}>{value}</span>
        {unit && <span className="inline-block text-sm leading-none text-muted-foreground [text-box:trim-both_cap_alphabetic]">{unit}</span>}
      </div>
      {label && captionBelow && <span className={quiet ? "text-xs leading-6 text-muted-foreground" : "text-sm leading-6"}>{label}</span>}
      {(delta || note) && (
        <div className="flex items-center gap-2">
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
