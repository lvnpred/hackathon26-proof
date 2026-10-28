import type * as React from 'react';

export type Tone = 'neutral' | 'ready' | 'recording' | 'info' | 'sun';

/** Top bar of every Lightday app. */
export interface AppBarProps {
  /** The app's job name, shown after the wordmark: "Clinic". */
  appName?: string;
  /** One line under it: the person or place, e.g. "Dr. [Doctor name]". */
  subtitle?: string;
  /** One status pill. */
  status?: { tone: Tone; label: string };
  /** Up to two Buttons. */
  actions?: React.ReactNode;
  className?: string;
}
export declare function AppBar(props: AppBarProps): React.ReactElement;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary: once per view (ink fill). ghost: default. quiet: text link style. danger: destructive. */
  variant?: 'primary' | 'ghost' | 'quiet' | 'danger';
  size?: 'md' | 'lg';
  /** Built-in line icon shown before the label. */
  icon?: 'mic' | 'stop' | 'arrow';
  /** Stretch to the container's width. */
  block?: boolean;
}
export declare function Button(props: ButtonProps): React.ReactElement;

export interface MicButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onToggle'> {
  /** true while capturing voice: turns record red and pulses. */
  recording?: boolean;
  /** Called on tap; the parent owns the recording state. */
  onToggle?: () => void;
  /** Visible label under the glyph. Defaults to "Dictate" / "Stop". */
  label?: string;
}
export declare function MicButton(props: MicButtonProps): React.ReactElement;

export interface StatusPillProps { tone?: Tone; children: React.ReactNode; className?: string }
export declare function StatusPill(props: StatusPillProps): React.ReactElement;

export interface FieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Visible label, always shown. */
  label: string;
  /** Helper line under the input. */
  hint?: string;
}
export declare function Field(props: FieldProps): React.ReactElement;

export interface CardProps { title?: string; tone?: 'surface' | 'sunk'; children?: React.ReactNode; className?: string }
export declare function Card(props: CardProps): React.ReactElement;

export interface ListRowProps {
  title: string;
  /** One line of metadata: "OP-1042 · 45 M · 10:20 am". */
  meta?: string;
  /** One word on the right: Open, Saved. */
  tag?: string;
  selected?: boolean;
  onClick?: () => void;
  className?: string;
}
export declare function ListRow(props: ListRowProps): React.ReactElement;

export interface SpokenGuideStep { say: string; example?: string }
export interface SpokenGuideProps {
  title?: string;
  steps: SpokenGuideStep[];
  /** 1-based number of the step being dictated; 0 = none. Steps before it show as done. */
  active?: number;
  className?: string;
}
export declare function SpokenGuide(props: SpokenGuideProps): React.ReactElement;

export interface PaperSheetProps {
  /** Letterhead text. Defaults to a placeholder that points to Profile. */
  letterhead?: React.ReactNode;
  /** Document title, set in caps serif. */
  title?: string;
  fields?: { label: string; value?: string }[];
  sections?: { heading: string; text?: string; listening?: boolean }[];
  /** Text for an empty section. Defaults to "Not dictated yet". */
  emptyText?: string;
  children?: React.ReactNode;
  className?: string;
}
export declare function PaperSheet(props: PaperSheetProps): React.ReactElement;

export interface AppTileProps {
  name: string;
  /** What the app does, one sentence. */
  job?: string;
  /** Per-use cost, e.g. "₹[price] per prescription". */
  price?: string;
  status?: { tone: Tone; label: string };
  /** Letter on the tile; defaults to the name's first letter. */
  initial?: string;
  href?: string;
  className?: string;
}
export declare function AppTile(props: AppTileProps): React.ReactElement;

export declare function Mark(props: { size?: number }): React.ReactElement;

declare global {
  interface Window {
    Lightday: {
      AppBar: typeof AppBar; Button: typeof Button; MicButton: typeof MicButton; StatusPill: typeof StatusPill;
      Field: typeof Field; Card: typeof Card; ListRow: typeof ListRow; SpokenGuide: typeof SpokenGuide;
      PaperSheet: typeof PaperSheet; AppTile: typeof AppTile; Mark: typeof Mark;
    };
  }
}
