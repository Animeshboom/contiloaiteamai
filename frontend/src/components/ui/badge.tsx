import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "border-border bg-muted text-muted-foreground",
        amber: "border-primary/30 bg-primary/10 text-primary",
        blue: "border-info/30 bg-info/10 text-info",
        green: "border-success/30 bg-success/10 text-success",
        red: "border-destructive/30 bg-destructive/10 text-destructive",
        yellow: "border-warning/30 bg-warning/10 text-warning",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
)

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {
  dot?: boolean
}

export function Badge({ className, tone, dot, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ tone }), className)} {...props}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}
