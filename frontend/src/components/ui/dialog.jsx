import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"

const Dialog = DialogPrimitive.Root

const DialogTrigger = DialogPrimitive.Trigger

const DialogPortal = DialogPrimitive.Portal

const DialogClose = DialogPrimitive.Close

const DialogOverlay = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/70 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props} />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

// Bottom sheet, not a centered card — matches the app's existing actions-sheet
// convention (ArticlePage's ⋯ menu) so every "thing slides up from an edge"
// moment in the app behaves the same way.
const DialogContent = React.forwardRef(({ className, children, style, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      style={{
        position: 'fixed',
        left: 0,
        right: 0,
        bottom: 0,
        margin: '0 auto',
        maxHeight: 'calc(100dvh - var(--sat, 44px) - 40px)',
        overflowY: 'auto',
        zIndex: 50,
        ...style,
      }}
      className={cn(
        "grid w-full max-w-lg gap-4 border-t border-x-0 border-b-0 border-white/10 bg-[#131211] p-5 shadow-lg duration-300 rounded-t-[20px] rounded-b-none",
        "data-[state=open]:animate-in data-[state=closed]:animate-out",
        "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
        "data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
        className
      )}
      {...props}>
      <div style={{ width: '34px', height: '4px', borderRadius: '2px', background: 'rgba(255,255,255,0.15)', margin: '-8px auto 2px' }} />
      {children}
      <DialogPrimitive.Close
        style={{
          position: 'absolute',
          right: '14px',
          top: '14px',
          background: 'rgba(255,255,255,0.06)',
          border: 'none',
          borderRadius: '50%',
          width: '30px',
          height: '30px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          flexShrink: 0,
        }}>
        <X size={14} color="#9A938A" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
))
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col space-y-1.5 text-center sm:text-left", className)}
    {...props} />
)
DialogHeader.displayName = "DialogHeader"

const DialogFooter = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2", className)}
    {...props} />
)
DialogFooter.displayName = "DialogFooter"

const DialogTitle = React.forwardRef(({ className, style, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontWeight: 600, fontSize: '19px', color: '#F2EEE9', ...style }}
    className={cn("leading-tight", className)}
    {...props} />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props} />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}
