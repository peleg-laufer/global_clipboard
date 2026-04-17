// =============================================================================
// global_clipboard — Flutter front-end (single file, tutorial edition)
// =============================================================================
//
// THIS FILE IS HEAVILY COMMENTED ON PURPOSE.
// If you already know Flutter/Dart, the comments will feel like noise — that's
// fine, the code itself is short. The comments are written for someone coming
// from Python/Java who has never touched JS or Dart.
//
// -----------------------------------------------------------------------------
// MENTAL MODEL OF FLUTTER (read this once, the rest will make sense)
// -----------------------------------------------------------------------------
//
// 1. EVERYTHING IS A WIDGET.
//    A "widget" is just a Dart object that describes a piece of UI: a button,
//    a piece of text, a column, a whole screen, the entire app. Widgets nest
//    inside other widgets to form a TREE (the "widget tree").
//
//    Think of it like HTML, but written as Dart constructor calls instead of
//    tags. Or think of it like a Java Swing component tree, but immutable.
//
// 2. WIDGETS ARE IMMUTABLE AND CHEAP.
//    You never "change" a widget. When the UI needs to update, Flutter throws
//    away the old widget objects and BUILDS A NEW TREE. That sounds wasteful,
//    but widgets are tiny config objects — the actual on-screen pixels are
//    managed separately and only re-painted where needed.
//
// 3. STATELESS vs STATEFUL.
//    - StatelessWidget: pure function of its inputs. Same inputs → same UI.
//      Use it when the widget never needs to remember anything.
//    - StatefulWidget: has a companion `State` object that can hold mutable
//      data (like the current text in a textbox). When you call `setState`,
//      Flutter knows to rebuild this widget's subtree.
//
// 4. THE `build` METHOD IS THE HEART OF EVERY WIDGET.
//    It returns a NEW widget tree describing what should be on screen RIGHT
//    NOW, given the current state. Flutter calls it whenever something
//    relevant changes.
//
// 5. DART SYNTAX QUIRKS YOU'LL SEE BELOW:
//    - `const` before a constructor → "this object never changes, Flutter can
//      cache it." Sprinkle it on widgets that have no dynamic data.
//    - `final` before a variable → "assign once, never reassign" (like Java's
//      `final`).
//    - Named arguments with `{...}` in constructors, called like
//      `Widget(name: value, other: value)`. Required ones use `required`.
//    - `super.key` → passes a `key` argument up to the parent class. Keys help
//      Flutter tell widgets apart when rebuilding lists. Ignore for now.
//    - `?` after a type → nullable (like Kotlin). `String?` = String or null.
//    - `late` → "I promise to assign this before anyone reads it."
//    - `_` prefix on a name → private to this file (Dart's only access modifier).
//    - `=>` is a one-line function shorthand: `int square(int x) => x * x;`
//
// -----------------------------------------------------------------------------
// HOW THIS APP IS STRUCTURED
// -----------------------------------------------------------------------------
//
//   main()                   ← Dart entry point. Boots the app.
//     └─ GlobalClipApp       ← Stateless. Sets up theme + picks the home screen.
//          └─ HomePage       ← Stateful. The actual screen the user sees.
//               ├─ AppBar    ← Top bar with the title.
//               └─ body:
//                    ├─ Row [Save] [Undo]    ← Buttons (not wired yet).
//                    ├─ TextField            ← The editable clipboard text.
//                    └─ Row of _SlotCard×3   ← Three file slots.
//
// =============================================================================

// `import` brings in code from another file or package.
// `package:flutter/material.dart` is the standard widget library that gives us
// MaterialApp, Scaffold, Text, Column, Button, etc. — all the Material Design
// widgets. (There's also a Cupertino library for iOS-style widgets.)
import 'package:flutter/material.dart';

// Top-level constant. Visible from anywhere in this file.
// We hard-code 3 slots to match the backend's slot model (slots 0, 1, 2).
const int numSlots = 3;

// `main` is the Dart entry point — same idea as Python's `if __name__ == '__main__'`
// or Java's `public static void main`. Flutter requires you to call `runApp`
// here, passing the ROOT widget of your app.
void main() {
  runApp(const GlobalClipApp());
}

// -----------------------------------------------------------------------------
// GlobalClipApp — the root of the widget tree.
// -----------------------------------------------------------------------------
// StatelessWidget because the app shell never needs to change at runtime.
// Its only job is to wrap everything in a `MaterialApp`, which provides:
//   - the theme (colors, typography)
//   - navigation/routing infrastructure
//   - the title shown in OS task switchers
class GlobalClipApp extends StatelessWidget {
  // Constructor. `const` means instances are compile-time constants — Flutter
  // can reuse the same instance instead of allocating a new one each rebuild.
  // `super.key` forwards the optional `key` parameter to the parent class.
  const GlobalClipApp({super.key});

  // Every widget MUST implement `build`. It returns the widget tree to display.
  // `BuildContext` is a handle to this widget's location in the tree — you use
  // it to look up things like the current theme or to navigate to other pages.
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Global Clipboard',
      // ThemeData controls colors/fonts app-wide. `colorScheme.fromSeed` picks
      // a coherent palette from a single base color (deepPurple here). M3 =
      // Material Design 3, the modern look.
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      // `home` is the default screen shown when the app starts.
      home: const HomePage(),
    );
  }
}

// -----------------------------------------------------------------------------
// HomePage — the only screen in the app.
// -----------------------------------------------------------------------------
// StatefulWidget because the textbox and (eventually) the slot data CHANGE
// while the app is running. The widget itself is still immutable; the mutable
// data lives in the companion State class below.
//
// A StatefulWidget is just two classes glued together:
//   1. The widget itself (this class) — describes "what kind of thing this is."
//   2. The State (`_HomePageState` below) — holds the mutable data and the
//      `build` method.
class HomePage extends StatefulWidget {
  const HomePage({super.key});

  // `createState` is called once by Flutter when this widget first appears.
  // It returns the State object that will live for as long as this widget is
  // mounted in the tree.
  @override
  State<HomePage> createState() => _HomePageState();
}

// The leading underscore makes this class private to this file.
// `State<HomePage>` tells Flutter "this state belongs to a HomePage widget."
class _HomePageState extends State<HomePage> {
  // -------------------------------------------------------------------------
  // STATE FIELDS — mutable data that survives across rebuilds.
  // -------------------------------------------------------------------------
  //
  // `TextEditingController` is Flutter's bridge between your Dart code and a
  // visible TextField. You read what the user typed via `_textController.text`
  // and you can also overwrite it (e.g., when Undo returns previous text).
  //
  // Think of it like holding a reference to the TextField's underlying buffer.
  final TextEditingController _textController = TextEditingController();

  // `dispose` is the State's "destructor." Flutter calls it when this screen
  // is permanently removed. We must release the controller to avoid leaking
  // memory and listeners. Always call `super.dispose()` LAST.
  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  // Event handlers for the two buttons. Empty for now — Step 3 will wire
  // them to the FastAPI backend (POST /text and POST /text/undo).
  void _onSavePressed() {
    // Step 3 will wire this.
  }

  void _onUndoPressed() {
    // Step 3 will wire this.
  }

  // -------------------------------------------------------------------------
  // build() — describes what's on screen, given current state.
  // -------------------------------------------------------------------------
  // Flutter calls this every time the state changes (and on first display).
  // We return a fresh tree of widget objects each time; Flutter diffs against
  // the previous tree to figure out the minimal screen update.
  @override
  Widget build(BuildContext context) {
    // Scaffold is the standard Material page layout: it gives you slots for
    // an app bar, a body, a floating action button, etc.
    return Scaffold(
      // The bar at the top of the screen.
      appBar: AppBar(title: const Text('Global Clipboard')),
      // The main content area. We wrap it in Padding so nothing touches the
      // window edges. EdgeInsets.all(16) = 16 logical pixels on every side.
      body: Padding(
        padding: const EdgeInsets.all(16),
        // Column lays its children out vertically (top → bottom).
        // `crossAxisAlignment: stretch` means children fill the column's WIDTH
        // (the cross axis of a vertical column is horizontal).
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ---- Row of action buttons (Save + Undo) ------------------------
            // Row lays its children out horizontally (left → right).
            Row(
              children: [
                // FilledButton = a "primary action" button (solid background).
                // `.icon` constructor adds a leading icon next to the label.
                FilledButton.icon(
                  onPressed: _onSavePressed,
                  icon: const Icon(Icons.save),
                  label: const Text('Save'),
                ),
                // SizedBox with only `width` is a horizontal spacer.
                const SizedBox(width: 8),
                // OutlinedButton = "secondary action" (just a border).
                OutlinedButton.icon(
                  onPressed: _onUndoPressed,
                  icon: const Icon(Icons.undo),
                  label: const Text('Undo'),
                ),
              ],
            ),

            // SizedBox with only `height` is a vertical spacer.
            const SizedBox(height: 8),

            // ---- Editable clipboard text -----------------------------------
            // We constrain the textbox to a fixed 200px tall. Inside, the
            // TextField uses `expands: true` to fill that 200px (otherwise it
            // would shrink to one line of text height).
            SizedBox(
              height: 200,
              child: TextField(
                controller: _textController,    // bind to our state buffer
                maxLines: null,                  // unlimited lines (multi-line)
                expands: true,                   // fill parent's available height
                textAlignVertical: TextAlignVertical.top, // cursor starts top
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  hintText: 'Clipboard text...', // shown when field is empty
                ),
              ),
            ),

            // Spacer eats up any remaining vertical space, pushing the slot
            // row down to the bottom of the window. (Without it, the row
            // would sit right under the textbox.)
            const Spacer(),

            // ---- Row of three file slots -----------------------------------
            // Inside a Row, `Expanded` makes a child grab an equal share of
            // the available width. So three Expanded children = three equal
            // columns. SizedBox(width: 12) adds gaps between them.
            //
            // The `for` loop below is a "collection-for" — Dart lets you put
            // a `for` directly inside a list literal to generate elements.
            // The `...[ ]` syntax SPREADS the inner list into the outer one
            // (so each iteration adds two items: the card + maybe a spacer).
            Row(
              children: [
                for (int i = 0; i < numSlots; i++) ...[
                  Expanded(child: _SlotCard(slot: i)),
                  // Add a spacer between slots, but not after the last one.
                  if (i < numSlots - 1) const SizedBox(width: 12),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// -----------------------------------------------------------------------------
// _SlotCard — one of the three file slot tiles.
// -----------------------------------------------------------------------------
// Stateless: it just renders whatever data it's given. When we wire up the
// real slot data in Step 4, it'll receive a `FileMeta?` instead of just an
// int and rebuild whenever the parent's state changes.
class _SlotCard extends StatelessWidget {
  // `final` field means it's set once in the constructor and never reassigned.
  // The slot index (0, 1, or 2). For now we just display it as a label.
  final int slot;

  // Constructor with a named, required parameter.
  // `required this.slot` is shorthand for "take a `slot` argument and assign
  // it to the field of the same name."
  const _SlotCard({required this.slot});

  @override
  Widget build(BuildContext context) {
    // Card = a Material surface with rounded corners and a subtle shadow.
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          // mainAxisSize.min = the column shrinks to fit its children's
          // combined height (instead of stretching to fill its parent).
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // String interpolation: `$slot` inlines the variable's value.
            // For expressions you'd use `${expr}`. Same idea as Python f-strings.
            Text('Slot $slot',
                // `Theme.of(context)` walks up the widget tree to find the
                // nearest Theme and grab its text styles. This is how widgets
                // pick up app-wide styling without you passing it explicitly.
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            // Placeholder area — will become the file name + size + drop zone
            // in Steps 4 and 5.
            const SizedBox(
              height: 80,
              child: Center(child: Text('(empty)\ndrop file here',
                  textAlign: TextAlign.center)),
            ),
            const SizedBox(height: 8),
            // `onPressed: null` makes Flutter render the button as DISABLED
            // (greyed out, not clickable). We'll enable it in Step 6 once we
            // know whether the slot actually has a file to download.
            OutlinedButton.icon(
              onPressed: null,
              icon: const Icon(Icons.download),
              label: const Text('Download'),
            ),
          ],
        ),
      ),
    );
  }
}
