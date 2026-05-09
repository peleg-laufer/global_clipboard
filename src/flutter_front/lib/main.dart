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

import 'dart:typed_data'; // Uint8List — needed for raw byte buffers (download response, file picker)
import 'package:flutter/material.dart';

// [ADDED] Import dio — the HTTP client library we use to talk to the FastAPI backend.
// Think of it like Python's `requests` library: you create a client, give it a
// base URL and timeouts, and then call .get() / .post() / etc.
import 'package:dio/dio.dart';

// [ADDED] desktop_drop — provides the DropTarget widget, which listens for files
// dragged from the OS file manager and dropped onto a UI region.
import 'package:desktop_drop/desktop_drop.dart';

// [ADDED] cross_file — XFile is a cross-platform file abstraction. desktop_drop
// gives us dropped files as XFile objects; we use xFile.readAsBytes() to get
// the raw bytes, which works on both web (Chrome) and native (no real file path
// is available in a browser sandbox).
import 'package:cross_file/cross_file.dart';

// [ADDED] file_saver — cross-platform "save bytes to disk".
// On web it creates a blob URL and clicks a hidden <a download> element (browser Save-As).
// On native it writes the bytes to the Downloads folder.
// One API, no platform-branching code needed in this file.
import 'package:file_saver/file_saver.dart';

// [ADDED] file_picker — cross-platform file-picker dialog (web + Windows + iPad + Android).
// Returns picked file as a PlatformFile with .bytes (when withData:true) and .name.
import 'package:file_picker/file_picker.dart';


// =============================================================================
// [ADDED] NETWORK CONFIGURATION
// =============================================================================
//
// A single constant for the server's base URL — the same idea as `constants.py`
// on the backend. Change this one line when you move from local dev to the Pi.
//
// `const` at the top level = a compile-time constant visible everywhere in
// this file (and importable by other files). No class wrapper needed.
const String kBaseUrl = 'http://localhost:8000';

// [ADDED] One shared Dio HTTP client for the entire app.
//
// `Dio(BaseOptions(...))` is like creating a `requests.Session` in Python with
// preset headers and timeouts. Every `.get()` / `.post()` call made through
// this instance inherits those settings automatically.
//
// Why `final` and not `const`? `const` requires the value to be known at
// compile time. Dio(...) is constructed at runtime, so `final` is correct —
// it means "assign once, never reassign."
//
// Why top-level? So any widget in this file can reach it without passing it
// down the widget tree. For a larger app you'd use a dependency-injection
// package (like Riverpod), but one file → top-level is fine.
final Dio _dio = Dio(
  BaseOptions(
    baseUrl: kBaseUrl,
    // How long to wait when opening the TCP connection to the server.
    connectTimeout: const Duration(seconds: 5),
    // How long to wait for the server to START sending a response.
    receiveTimeout: const Duration(seconds: 10),
  ),
);


// =============================================================================
// [ADDED] DATA MODEL — mirrors the Python `PublicFileMeta` Pydantic model
// =============================================================================
//
// The FastAPI backend returns JSON like:
//   {
//     "file_name": "photo.png",
//     "file_type": "image/png",
//     "file_size": 204800,
//     "file_uuid": "abc-123",
//     "file_slot": 0
//   }
//
// In Python, Pydantic validates and serialises this automatically. In Dart we
// write the mapping by hand in a named constructor called `fromJson`.
//
// `fromJson` is a Dart convention (not a keyword). It takes a `Map<String,
// dynamic>` — which is what Dio gives us after parsing the JSON response body
// — and assigns each key to a typed field.
class FileMeta {
  final String fileName;  // original filename, e.g. "report.pdf"
  final String fileType;  // MIME type, e.g. "application/pdf"
  final int    fileSize;  // size in bytes
  final String fileUuid;  // server-assigned unique ID
  final int    fileSlot;  // 0, 1, or 2

  FileMeta.fromJson(Map<String, dynamic> json)
      : fileName = json['file_name'] as String,
        fileType = json['file_type'] as String,
        fileSize = json['file_size'] as int,
        fileUuid = json['file_uuid'] as String,
        fileSlot = json['file_slot'] as int;

  // A computed property (getter) that turns raw bytes into a human-readable
  // string. The `get` keyword means you read it like a field: `meta.readableSize`
  // — no parentheses needed, just like a @property in Python.
  String get readableSize {
    if (fileSize < 1024)             return '$fileSize B';
    if (fileSize < 1024 * 1024)      return '${(fileSize / 1024).toStringAsFixed(1)} KB';
    return '${(fileSize / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}


// =============================================================================
// TOP-LEVEL CONSTANTS
// =============================================================================

// Hard-code 3 slots to match the backend's slot model (slots 0, 1, 2).
const int numSlots = 3;


// =============================================================================
// ENTRY POINT
// =============================================================================

// `main` is the Dart entry point — same idea as Python's `if __name__ == '__main__'`
// or Java's `public static void main`. Flutter requires you to call `runApp`
// here, passing the ROOT widget of your app.
void main() {
  runApp(const GlobalClipApp());
}


// =============================================================================
// GlobalClipApp — the root of the widget tree. UNCHANGED.
// =============================================================================
// StatelessWidget because the app shell never needs to change at runtime.
// Its only job is to wrap everything in a `MaterialApp`, which provides:
//   - the theme (colors, typography)
//   - navigation/routing infrastructure
//   - the title shown in OS task switchers
class GlobalClipApp extends StatelessWidget {
  const GlobalClipApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Global Clipboard',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      home: const HomePage(),
    );
  }
}


// =============================================================================
// HomePage — the only screen in the app. UNCHANGED except button stubs.
// =============================================================================
// StatefulWidget because the textbox and slot data CHANGE while the app runs.
class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  // `TextEditingController` is Flutter's bridge between your Dart code and a
  // visible TextField. Read the user's text via `_textController.text`; write
  // to it (e.g. after Undo) by assigning `_textController.text = newValue`.
  final TextEditingController _textController = TextEditingController();

  // [ADDED] True while the initial GET /text fetch is in flight.
  // Drives a loading indicator over the TextField so the user knows their
  // previously saved text is on its way.
  bool _isTextLoading = true;

  // ---------------------------------------------------------------------------
  // [ADDED] LIFECYCLE — initState
  // ---------------------------------------------------------------------------
  // Called once when the screen first appears. Kicks off the initial text fetch.
  @override
  void initState() {
    super.initState();
    _fetchText();
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------------------------
  // [ADDED] GET /text — load the last saved clipboard text on startup.
  // ---------------------------------------------------------------------------
  // 200 → pre-fill the TextField with the returned text.
  // 204 → no saves exist yet; leave the TextField empty.
  // Error → silently clear the loading indicator (text stays empty).
  //         A SnackBar / error banner can be added in a later step.
  Future<void> _fetchText() async {
    try {
      final response = await _dio.get('/text');
      if (response.statusCode == 200 && response.data != null) {
        // Assigning to _textController.text updates the visible TextField.
        // We still call setState so _isTextLoading flips — but note that
        // TextEditingController notifies its own listeners too, so the
        // TextField repaints without setState even if we forget it here.
        setState(() {
          _textController.text = response.data['text'] as String;
        });
      }
      // 204 No Content → history is empty, nothing to fill in.
    } on DioException catch (_) {
      // Network / server error — leave the field empty.
      // `_` discards the exception object we don't need to inspect.
    } finally {
      // `finally` runs whether the try succeeded or the catch fired.
      // Always clear the loading flag so the spinner goes away.
      setState(() => _isTextLoading = false);
    }
  }

  // ---------------------------------------------------------------------------
  // [ADDED] POST /text — save the current TextField content to the server.
  // ---------------------------------------------------------------------------
  // The backend only stores it if the text differs from the last save,
  // so duplicate taps are harmless.
  Future<void> _onSavePressed() async {
    try {
      await _dio.post('/text', data: {'text': _textController.text});
    } on DioException catch (_) {
      // Error handling (SnackBar etc.) will be added in a later step.
    }
  }

  // ---------------------------------------------------------------------------
  // [ADDED] POST /text/undo — revert the TextField to the previous save.
  // ---------------------------------------------------------------------------
  // 200 → replace TextField content with the returned text.
  // 204 → history is empty, nothing to undo; leave the field as-is.
  Future<void> _onUndoPressed() async {
    try {
      final response = await _dio.post('/text/undo');
      if (response.statusCode == 200 && response.data != null) {
        setState(() {
          _textController.text = response.data['text'] as String;
        });
      } else {
        // 204 → history is empty, DB has no text. Clear the field to match.
        setState(() => _textController.text = '');
      }
    } on DioException catch (_) {
      // Error handling to be added later.
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Global Clipboard')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ---- Row of action buttons (Save + Undo) ------------------------
            Row(
              children: [
                FilledButton.icon(
                  onPressed: _onSavePressed,
                  icon: const Icon(Icons.save),
                  label: const Text('Save'),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: _onUndoPressed,
                  icon: const Icon(Icons.undo),
                  label: const Text('Undo'),
                ),
              ],
            ),

            const SizedBox(height: 8),

            // ---- Editable clipboard text ------------------------------------
            // [CHANGED] Wrapped in a Stack so we can overlay a spinner while
            // the initial GET /text fetch is in flight.
            //
            // Stack layers its children on top of each other (like CSS
            // position:absolute). The TextField is always rendered underneath;
            // the spinner sits on top and disappears once _isTextLoading is false.
            SizedBox(
              height: 200,
              child: Stack(
                children: [
                  TextField(
                    controller: _textController,
                    maxLines: null,
                    expands: true,
                    textAlignVertical: TextAlignVertical.top,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      hintText: 'Clipboard text...',
                    ),
                  ),
                  // Show a centered spinner only while loading.
                  // `if` inside a list literal is valid Dart — it conditionally
                  // includes the widget in the children list.
                  if (_isTextLoading)
                    const Center(child: CircularProgressIndicator()),
                ],
              ),
            ),

            const Spacer(),

            // ---- Row of three file slots ------------------------------------
            Row(
              children: [
                for (int i = 0; i < numSlots; i++) ...[
                  Expanded(child: _SlotCard(slot: i)),
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


// =============================================================================
// _SlotCard — one of the three file slot tiles.
// [CHANGED] Was StatelessWidget. Now StatefulWidget so it can:
//   1. Fire GET /files/{slot} when it first appears on screen.
//   2. Hold the result (file metadata, loading flag, error message).
//   3. Rebuild itself when that data arrives or changes.
// =============================================================================
//
// A StatefulWidget is split into two classes:
//   • The widget class (_SlotCard) — immutable config: just the slot index.
//   • The state class (_SlotCardState) — mutable data + the build() method.
//
// Flutter keeps the State object alive across rebuilds; the widget object is
// thrown away and recreated freely (it's just a config record).
class _SlotCard extends StatefulWidget {
  final int slot;
  const _SlotCard({required this.slot});

  @override
  State<_SlotCard> createState() => _SlotCardState();
}

class _SlotCardState extends State<_SlotCard> {

  // ---------------------------------------------------------------------------
  // [ADDED] STATE FIELDS
  // ---------------------------------------------------------------------------
  //
  // `FileMeta?` — the `?` means nullable (Dart's equivalent of Optional<T> in
  // Java, or `T | None` in Python). Null here means "slot is empty" or "fetch
  // hasn't completed yet" — we use _isLoading to tell the two cases apart.
  FileMeta? _fileMeta;

  // True while the GET /files/{slot} request is in flight.
  // Drives a spinner in the UI so the user knows something is happening.
  bool _isLoading = true;

  // Non-null when the last network call failed. Shown as a red error string.
  String? _errorMessage;


  // ---------------------------------------------------------------------------
  // [ADDED] LIFECYCLE — initState
  // ---------------------------------------------------------------------------
  //
  // `initState` is called ONCE, the moment this State is first inserted into
  // the widget tree (analogous to __init__ or a constructor body in Python).
  // It's the right place to kick off a one-time fetch.
  //
  // It must be synchronous, so we call an async helper and let it run in the
  // background. Flutter is fine with this — the widget rebuilds each time
  // _fetchSlotMeta calls setState() with updated data.
  @override
  void initState() {
    super.initState(); // always call super first in lifecycle methods
    _fetchSlotMeta();
  }


  // ---------------------------------------------------------------------------
  // [ADDED] NETWORK METHOD — GET /files/{slot}
  // ---------------------------------------------------------------------------
  //
  // `async` / `await` in Dart work exactly like Python's asyncio:
  //   - `async` marks a function as asynchronous.
  //   - `await` suspends execution until a Future (≈ Python coroutine) resolves.
  //   - `Future<void>` is the return type for an async function that returns nothing.
  //
  // Response codes we care about:
  //   200 → file exists, parse JSON into FileMeta
  //   204 → slot is empty, keep _fileMeta null
  //   anything else → Dio throws a DioException (handled in catch)
  Future<void> _fetchSlotMeta() async {
    // Signal "loading started" and clear any previous error.
    setState(() {
      _isLoading    = true;
      _errorMessage = null;
    });

    try {
      // `widget` inside a State refers back to the paired StatefulWidget.
      // We access `widget.slot` here because State doesn't store slot itself.
      final response = await _dio.get('/files/${widget.slot}');

      setState(() {
        if (response.statusCode == 200 && response.data != null) {
          // `response.data` is already a Map<String, dynamic> — Dio parses
          // the JSON body automatically when the Content-Type is application/json.
          _fileMeta = FileMeta.fromJson(response.data as Map<String, dynamic>);
        } else {
          // 204 No Content → slot is empty
          _fileMeta = null;
        }
        _isLoading = false;
      });

    } on DioException catch (e) {
      // DioException wraps network failures, timeouts, and HTTP error codes.
      // We surface a short message to the user rather than silently swallowing it.
      setState(() {
        _errorMessage = e.message ?? 'Network error';
        _isLoading    = false;
      });
    }
  }


  // ---------------------------------------------------------------------------
  // [ADDED] DROP HANDLER — entry point for all drag-and-drop interactions.
  // ---------------------------------------------------------------------------
  // Called by DropTarget's onDragDone when the user drops a file onto the card.
  // Decides whether this is a fresh upload (slot empty) or a replace (slot taken),
  // and shows a confirmation dialog before overwriting an existing file.
  //
  // `async` because both the dialog and the network calls are asynchronous.
  // `mounted` is a built-in State property — it's false if the widget was removed
  // from the tree while we were awaiting something. Always check it before calling
  // setState or using context after an await, or Flutter will throw an error.
  Future<void> _onFileDrop(XFile xFile) async {
    if (_fileMeta == null) {
      // Slot is empty — upload straight away.
      await _uploadFile(xFile);
    } else {
      // Slot is occupied — ask the user before overwriting.
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Replace file?'),
          content: Text(
            'Slot ${widget.slot} already has "${_fileMeta!.fileName}".\nReplace it?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Replace'),
            ),
          ],
        ),
      );
      // `confirmed` is null if the user dismissed the dialog by tapping outside —
      // treat that the same as Cancel.
      if (confirmed == true && mounted) await _replaceFile(xFile);
    }
  }

  // ---------------------------------------------------------------------------
  // [ADDED] POST /files?slot={slot} — upload a file to an empty slot.
  // ---------------------------------------------------------------------------
  // `slot` is a query parameter on this endpoint (not a path segment), so we
  // pass it via `queryParameters` rather than embedding it in the URL string.
  //
  // The file is sent as multipart/form-data. The field name `uploaded_file` must
  // match the FastAPI parameter name exactly, or the server returns a 422.
  //
  // We read the file as bytes (`readAsBytes`) instead of using a file path because
  // on web (Chrome) there is no real file-system path — the browser gives us only
  // an in-memory buffer.
  Future<void> _uploadFile(XFile xFile) async {
    setState(() { _isLoading = true; _errorMessage = null; });
    try {
      final bytes = await xFile.readAsBytes();
      final formData = FormData.fromMap({
        'uploaded_file': MultipartFile.fromBytes(bytes, filename: xFile.name),
      });
      final response = await _dio.post(
        '/files',
        queryParameters: {'slot': widget.slot},
        data: formData,
      );
      if (mounted) {
        setState(() {
          _fileMeta  = FileMeta.fromJson(response.data as Map<String, dynamic>);
          _isLoading = false;
        });
      }
    } on DioException catch (e) {
      if (mounted) setState(() { _errorMessage = e.message ?? 'Upload failed'; _isLoading = false; });
    }
  }

  // ---------------------------------------------------------------------------
  // [ADDED] PUT /files/{slot}/replace — swap the file in an occupied slot.
  // ---------------------------------------------------------------------------
  // Same multipart/form-data shape as upload, but the field name is `new_file`
  // to match the FastAPI PUT endpoint's parameter name.
  Future<void> _replaceFile(XFile xFile) async {
    setState(() { _isLoading = true; _errorMessage = null; });
    try {
      final bytes = await xFile.readAsBytes();
      final formData = FormData.fromMap({
        'new_file': MultipartFile.fromBytes(bytes, filename: xFile.name),
      });
      final response = await _dio.put(
        '/files/${widget.slot}/replace',
        data: formData,
      );
      if (mounted) {
        setState(() {
          _fileMeta  = FileMeta.fromJson(response.data as Map<String, dynamic>);
          _isLoading = false;
        });
      }
    } on DioException catch (e) {
      if (mounted) setState(() { _errorMessage = e.message ?? 'Replace failed'; _isLoading = false; });
    }
  }

  // ---------------------------------------------------------------------------
  // [ADDED] DELETE /files/{slot} — remove the file and empty the slot.
  // ---------------------------------------------------------------------------
  Future<void> _deleteFile() async {
    setState(() { _isLoading = true; _errorMessage = null; });
    try {
      await _dio.delete('/files/${widget.slot}');
      if (mounted) setState(() { _fileMeta = null; _isLoading = false; });
    } on DioException catch (e) {
      if (mounted) setState(() { _errorMessage = e.message ?? 'Delete failed'; _isLoading = false; });
    }
  }

  // ---------------------------------------------------------------------------
  // [ADDED] GET /files/{slot}/download — fetch bytes and save to disk.
  // ---------------------------------------------------------------------------
  // `responseType: ResponseType.bytes` tells Dio to give us the raw response
  // body as a Uint8List instead of trying to parse it as JSON. Required for
  // binary file content.
  //
  // FileSaver.instance.saveFile abstracts the platform difference:
  //   • Web  → creates a Blob URL, clicks a hidden <a download> element →
  //            browser shows its native "Save As" dialog.
  //   • Native → writes the bytes to the system Downloads folder.
  Future<void> _onDownloadPressed() async {
    setState(() { _isLoading = true; _errorMessage = null; });
    try {
      final response = await _dio.get(
        '/files/${widget.slot}/download',
        options: Options(responseType: ResponseType.bytes),
      );
      await FileSaver.instance.saveFile(
        name: _fileMeta!.fileName,
        bytes: response.data as Uint8List,
      );
    } on DioException catch (e) {
      if (mounted) setState(() => _errorMessage = e.message ?? 'Download failed');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  // ---------------------------------------------------------------------------
  // [ADDED] BROWSE HANDLER — open an OS file-picker dialog.
  // ---------------------------------------------------------------------------
  // `withData: true` forces file_picker to read the bytes eagerly. This is
  // required on web (no real file path exists in the browser sandbox) and keeps
  // the code the same on native (slightly less efficient than path-based reading,
  // but acceptable for this app's file sizes).
  //
  // After picking, we build an XFile.fromData and hand it to _onFileDrop — so
  // the upload-vs-replace logic and the confirmation dialog are reused for free.
  Future<void> _onBrowsePressed() async {
    final result = await FilePicker.platform.pickFiles(withData: true);
    if (result == null || result.files.isEmpty) return; // user cancelled
    final pf = result.files.first;
    final xFile = XFile.fromData(
      pf.bytes!,
      name: pf.name,
      mimeType: pf.extension != null ? 'application/${pf.extension}' : null,
    );
    await _onFileDrop(xFile);
  }


  // ---------------------------------------------------------------------------
  // build() — what to draw, given current state.
  // ---------------------------------------------------------------------------
  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Slot ${widget.slot}',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),

            // [CHANGED] Wrapped in DropTarget so the 80px area accepts dragged files.
            // DropTarget is from package:desktop_drop. It wraps any widget and fires
            // onDragDone when the user releases a file over it. We forward the first
            // dropped file to _onFileDrop, which decides upload vs replace.
            DropTarget(
              onDragDone: (detail) => _onFileDrop(detail.files.first),
              child: SizedBox(
                height: 80,
                child: Center(child: _buildContent()),
              ),
            ),
            const SizedBox(height: 8),

            // [ADDED] Browse button — opens the OS file picker as an alternative
            // to drag-and-drop. Shares the same upload/replace/dialog logic.
            OutlinedButton.icon(
              onPressed: _onBrowsePressed,
              icon: const Icon(Icons.folder_open),
              label: const Text('Browse'),
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.blue,
              ),
            ),
            const SizedBox(height: 4),

            OutlinedButton.icon(
              onPressed: _fileMeta != null ? _onDownloadPressed : null,
              icon: const Icon(Icons.download),
              label: const Text('Download'),
            ),

            // [ADDED] Delete button — only rendered when the slot has a file.
            // `if` inside a list literal conditionally includes the widget.
            if (_fileMeta != null) ...[
              const SizedBox(height: 4),
              OutlinedButton.icon(
                onPressed: _deleteFile,
                icon: const Icon(Icons.delete_outline),
                label: const Text('Delete'),
                // Tint the button red to signal a destructive action.
                style: OutlinedButton.styleFrom(
                  foregroundColor: Theme.of(context).colorScheme.error,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }


  // ---------------------------------------------------------------------------
  // [ADDED] HELPER — decides what to render in the 80px content area.
  // ---------------------------------------------------------------------------
  //
  // Extracting this into a helper keeps build() clean and readable. This is
  // idiomatic Flutter: build() reads like a layout spec; helpers handle the
  // conditional logic. Think of it like a private render function.
  Widget _buildContent() {
    // 1. Still waiting for the server response.
    if (_isLoading) {
      return const CircularProgressIndicator();
    }

    // 2. Request finished but failed.
    if (_errorMessage != null) {
      return Text(
        'Error: $_errorMessage',
        textAlign: TextAlign.center,
        style: const TextStyle(color: Colors.red),
      );
    }

    // 3. Slot has a file — show its name and size.
    if (_fileMeta != null) {
      return Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // `overflow: ellipsis` truncates long filenames with "…" instead
          // of overflowing the card boundaries.
          Text(
            _fileMeta!.fileName,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
          ),
          Text(
            _fileMeta!.readableSize,
            style: const TextStyle(color: Colors.grey),
          ),
        ],
      );
    }

    // 4. Slot is empty and no error.
    return const Text('(empty)\ndrop file here', textAlign: TextAlign.center);
  }
}
