/** DienstPilot components: plain DOM factories on window.DienstPilot. Each returns an HTMLElement. Load css/dienstpilot-tokens.css, then components/bundle.css, then components/bundle.js. */
export type Lang = "de" | "en";
/** Canonical shift keys, or a letter in either language (F/S/N/B/R/U, E/L/N/O/H/V). "ruf" = Rufbereitschaft, on call from home. */
export type Shift = "frueh" | "spaet" | "nacht" | "bereitschaft" | "ruf" | "frei" | "F" | "S" | "N" | "B" | "R" | "U" | "E" | "L" | "O" | "H" | "V";

export interface ShiftChipProps { shift: Shift; lang?: Lang; size?: "sm" | "md" | "lg"; label?: boolean | string; time?: string; }
export interface RosterCellProps {
  lang?: Lang; shift?: Shift; wish?: "granted" | "missed"; violation?: boolean | string;
  gap?: Shift; leave?: boolean; suggested?: boolean; selected?: boolean; interactive?: boolean; onClick?: (e: MouseEvent) => void;
}
export interface RosterDay { d: number; wd: string; weekend?: boolean; today?: boolean; }
export interface RosterRow { name: string; role?: string; hours?: number; cells: Array<RosterCellProps | Shift | null>; }
export interface RosterGridProps { days: RosterDay[]; rows: RosterRow[]; coverage?: Array<"ok" | string | { gap: Shift } | null>; lang?: Lang; caption?: string; interactive?: boolean; legend?: boolean; rowLabel?: string; }
/** The 33 Lucide icons in the set (lucide-react names in PascalCase: Check, CircleSlash2, CircleAlert, Star, ...). See the brand book's Iconography tables. */
export type IconName =
  | "check" | "circle-slash-2" | "circle-alert" | "star" | "circle-check" | "shield-check"
  | "bell-ring" | "circle-x" | "timer-off"
  | "pencil-line" | "circle-question-mark" | "book-open-text" | "send-horizontal" | "panel-right"
  | "x" | "chevron-down" | "chevron-left" | "chevron-right" | "list-filter" | "download" | "external-link" | "flask-conical"
  | "layout-dashboard" | "calendar-clock" | "columns-3" | "calendar-days" | "inbox" | "user-x" | "scale" | "scroll-text" | "settings" | "eye" | "cpu";
export interface ButtonProps { label?: string; variant?: "primary" | "secondary" | "quiet" | "link" | "pencil"; size?: "md" | "lg"; block?: boolean; disabled?: boolean; href?: string; type?: "button" | "submit"; icon?: IconName; onClick?: (e: MouseEvent) => void; }
export interface FieldProps { label: string; value?: string; placeholder?: string; hint?: string; /** What is wrong, one sentence. */ error?: string; /** How to fix it. Required whenever `error` is set. */ fix?: string; options?: Array<string | { value: string; label: string }>; multiline?: boolean; numeric?: boolean; type?: string; id?: string; }
export interface CheckboxProps { label: string; hint?: string; checked?: boolean; name?: string; onChange?: (e: Event) => void; }
export interface SwitchProps { label: string; checked?: boolean; lang?: Lang; onChange?: (checked: boolean) => void; }
export interface SegmentedProps { options: Array<string | { value: string; label: string }>; value?: string; label?: string; name?: string; onChange?: (value: string) => void; }
export interface SuggestionReason { text: string; source?: string; }
export interface SuggestionProps { text: string; reasons?: SuggestionReason[]; lang?: Lang; accept?: string; dismiss?: string; note?: string; open?: boolean; inline?: boolean; onAccept?: () => void; onDismiss?: () => void; onWhy?: () => void; }
export interface RuleMessageProps { title: string; /** How to fix it. Required. */ detail: string; lang?: Lang; fix?: string | false; onFix?: () => void; }
export interface EnvBadgeProps { lang?: Lang; bar?: boolean; }

export declare function ShiftChip(p: ShiftChipProps): HTMLElement;
export declare function RosterCell(p: RosterCellProps): HTMLElement;
export declare function RosterGrid(p: RosterGridProps): HTMLElement;
export declare function Button(p: ButtonProps): HTMLElement;
export declare function Field(p: FieldProps): HTMLElement;
export declare function Checkbox(p: CheckboxProps): HTMLElement;
export declare function Switch(p: SwitchProps): HTMLElement;
export declare function Segmented(p: SegmentedProps): HTMLElement;
export declare function Suggestion(p: SuggestionProps): HTMLElement;
export declare function RuleMessage(p: RuleMessageProps): HTMLElement;
export declare function EnvBadge(p: EnvBadgeProps): HTMLElement;
/** A Lucide icon as inline SVG: outline, 1.75px stroke at any size (absoluteStrokeWidth), colour from currentColor.
 *  `filled` is only allowed for "star" (a wish marked important); any other icon throws. */
export declare function icon(name: IconName, size?: number, extraClass?: string | null, filled?: boolean): SVGSVGElement;
