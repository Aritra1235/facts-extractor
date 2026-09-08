"use client";

import { PanelLeft } from "lucide-react";
import {
  type ComponentProps,
  createContext,
  type ReactNode,
  useContext,
  useState,
} from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SidebarContext = createContext<{
  open: boolean;
  setOpen: (open: boolean) => void;
} | null>(null);

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <SidebarContext.Provider value={{ open, setOpen }}>
      {children}
    </SidebarContext.Provider>
  );
}

export function Sidebar({ className, ...props }: ComponentProps<"aside">) {
  const context = useContext(SidebarContext);
  return (
    <>
      {context?.open && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-slate-950/40 lg:hidden"
          onClick={() => context.setOpen(false)}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[268px] -translate-x-full flex-col bg-sidebar text-sidebar-foreground transition-transform duration-200 lg:translate-x-0",
          context?.open && "translate-x-0",
          className,
        )}
        {...props}
      />
    </>
  );
}

export function SidebarHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("p-4", className)} {...props} />;
}

export function SidebarContent({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("min-h-0 flex-1 overflow-y-auto px-3", className)}
      {...props}
    />
  );
}

export function SidebarFooter({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("p-4", className)} {...props} />;
}

export function SidebarInset({ className, ...props }: ComponentProps<"main">) {
  return (
    <main
      className={cn("min-h-screen w-full lg:pl-[268px]", className)}
      {...props}
    />
  );
}

export function SidebarMenuButton({
  active,
  className,
  onClick,
  ...props
}: ComponentProps<"button"> & { active?: boolean }) {
  const context = useContext(SidebarContext);
  return (
    <button
      type="button"
      onClick={(event) => {
        onClick?.(event);
        context?.setOpen(false);
      }}
      className={cn(
        "flex h-10 w-full items-center rounded-lg px-3 text-left text-sm font-medium text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        active && "bg-sidebar-accent text-sidebar-accent-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function SidebarTrigger() {
  const context = useContext(SidebarContext);
  return (
    <Button
      variant="ghost"
      size="icon"
      className="lg:hidden"
      aria-label="Open navigation"
      onClick={() => context?.setOpen(true)}
    >
      <PanelLeft />
    </Button>
  );
}
