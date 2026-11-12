;;; archvectra.lsp - ArchVectra inside AutoCAD
;;;
;;; Turns a scanned or vector architectural PDF into clean, layered AutoCAD
;;; geometry without leaving AutoCAD.  The image processing is done by the
;;; ArchVectra engine (archvectra.exe, Python/OpenCV); this file starts it in
;;; the background, waits, and brings the result into the current drawing.
;;;
;;; Load with APPLOAD (add to the Startup Suite to load automatically).
;;;
;;; Main commands
;;;   ARCHVECTRA            pick a PDF, enter page and scale -> vectorised geometry in this drawing
;;;   ARCHVECTRA-UNDERLAY   select an attached PDF underlay -> geometry placed exactly on top of it
;;;   ARCHVECTRA-SETUP      tell AutoCAD where archvectra.exe is (once per PC)
;;; Review / checking
;;;   ARCHVECTRA-REVIEW     step through Z-REVIEW flags (zoom to each, show message)
;;;   ARCHVECTRA-LOWCONF    select entities whose confidence is below a threshold
;;;   ARCHVECTRA-WALLS      list wall centrelines with measured thickness
;;;   ARCHVECTRA-CHECKDIM   compare a picked distance with an expected value
;;;   ARCHVECTRA-REPORT     open the review PDF / report of the last run
;;; Utilities
;;;   ARCHVECTRA-IMPORT     insert an existing ArchVectra DXF
;;;   ARCHVECTRA-LAYERS     apply ArchVectra layer standards
;;;   ARCHVECTRA-CLEAN      OVERKILL on linework layers
;;;
;;; STATUS: written against documented AutoLISP / Visual LISP / WScript
;;; functions; NOT yet executed in AutoCAD by its author - test on a copy first.
;;; Requires full AutoCAD or AutoCAD LT 2024+ on Windows (uses ActiveX).

(vl-load-com)

(setq *archvectra-layers*
  '(("A-WALL"        7 35 T)
    ("A-WALL-CNTR"   8 13 nil)
    ("A-COLS"        5 35 T)
    ("A-SOLID"       9 25 T)
    ("A-DETL"        7 18 T)
    ("A-DETL-ARC"    3 18 T)
    ("A-DOOR"        3 18 T)
    ("A-GLAZ"        4 18 T)
    ("A-OPEN"        6 13 nil)
    ("A-AREA-BDRY"  30 13 nil)
    ("A-ANNO"        2 13 T)
    ("A-ANNO-TEXT"   2 13 T)
    ("Z-REVIEW"      1 13 nil)))

(setq *archvectra-last-out* nil)   ; output folder of the last run in this session

;;; ================================================================ engine helpers
(defun archvectra:exe (/ p)
  ;; path of archvectra.exe saved by ARCHVECTRA-SETUP (stored in the AutoCAD profile)
  (setq p (getenv "ArchVectraExe"))
  (if (and p (/= p "") (findfile p)) p nil))

(defun archvectra:quote (s) (strcat "\"" s "\""))

(defun archvectra:shell-run (cmdline wait / sh rc)
  ;; run a command line hidden; returns the exit code when wait = T
  (setq sh (vlax-create-object "WScript.Shell"))
  (setq rc (vl-catch-all-apply 'vlax-invoke-method
                               (list sh 'Run cmdline (if wait 0 1) (if wait :vlax-true :vlax-false))))
  (vlax-release-object sh)
  (if (vl-catch-all-error-p rc)
    (progn (princ (strcat "\nCould not start: " (vl-catch-all-error-message rc))) nil)
    rc))

(defun archvectra:open-file (path)
  ;; open a file with its Windows default program (PDF viewer, text editor ...)
  (if (findfile path) (archvectra:shell-run (archvectra:quote path) nil)))

(defun archvectra:outdir (pdf)
  (strcat (vl-filename-directory pdf) "\\" (vl-filename-base pdf) "_archvectra"))

(defun archvectra:run-engine (pdf page scale / exe out args rc)
  ;; page is 1-based; scale = N for 1:N, or nil when unknown.  Returns output folder or nil.
  (setq exe (archvectra:exe))
  (cond
    ((not exe)
     (princ "\nArchVectra engine not found - run ARCHVECTRA-SETUP and select archvectra.exe.")
     nil)
    (T
     (setq out  (archvectra:outdir pdf)
           args (strcat "process " (archvectra:quote pdf)
                        " -o " (archvectra:quote out)
                        " --page " (itoa (1- page))
                        (if scale (strcat " --scale " (rtos scale 2 6)) "")))
     (princ (strcat "\nArchVectra: processing " (vl-filename-base pdf) ".pdf - please wait ..."))
     (princ)
     (setq rc (archvectra:shell-run (strcat (archvectra:quote exe) " " args) T))
     (cond
       ((null rc) nil)
       ((/= rc 0)
        (princ (strcat "\nArchVectra failed (exit code " (itoa rc) "). Details: " out "\\run.log"))
        nil)
       (T (setq *archvectra-last-out* out) out)))))

(defun archvectra:result-dxf (pdf out)
  (findfile (strcat out "\\02_vector\\" (vl-filename-base pdf) "_clean.dxf")))

(defun archvectra:show-summary (out / f fh line)
  (if (setq f (findfile (strcat out "\\summary.txt")))
    (progn
      (setq fh (open f "r"))
      (princ "\n---------------- ArchVectra result ----------------")
      (while (setq line (read-line fh))
        (if (not (wcmatch line "PAGE_MM *")) (princ (strcat "\n  " line))))
      (close fh)
      (princ "\n----------------------------------------------------"))))

(defun archvectra:page-mm (out / f fh line res)
  ;; (width height) of the PDF page in mm, read from summary.txt
  (if (setq f (findfile (strcat out "\\summary.txt")))
    (progn
      (setq fh (open f "r"))
      (while (setq line (read-line fh))
        (if (wcmatch line "PAGE_MM *")
          (setq res (read (strcat "(" (substr line 9) ")")))))
      (close fh)))
  res)

(defun archvectra:insert (dxf pt scl rot-deg / before oldecho ok)
  ;; insert DXF exploded; returns T when new entities were created
  (setq before (entlast) oldecho (getvar "CMDECHO"))
  (setvar "CMDECHO" 0)
  (command "_.-INSERT" (strcat "*" dxf) pt (rtos scl 2 10) (rtos rot-deg 2 8))
  (setvar "CMDECHO" oldecho)
  (setq ok (not (equal before (entlast))))
  (if ok
    (c:ARCHVECTRA-LAYERS)
    (princ (strcat "\nThe DXF could not be inserted automatically. Open it with OPEN or DXFIN:\n  " dxf)))
  ok)

(defun archvectra:after-import (out / ans)
  (archvectra:show-summary out)
  (princ "\nUse ARCHVECTRA-REVIEW to step through items that need checking.")
  (initget "Yes No")
  (setq ans (getkword "\nOpen the review PDF (reconstruction over the source)? [Yes/No] <No>: "))
  (if (= ans "Yes") (c:ARCHVECTRA-REPORT)))

;;; ================================================================ main commands
(defun c:ARCHVECTRA-SETUP (/ cur f)
  (setq cur (getenv "ArchVectraExe"))
  (if cur (princ (strcat "\nCurrent engine: " cur)))
  (setq f (getfiled "Locate archvectra.exe" (if cur cur "") "exe" 0))
  (if f
    (progn
      (setenv "ArchVectraExe" f)
      (princ (strcat "\nArchVectra engine set to: " f))
      (if (/= 0 (archvectra:shell-run (strcat (archvectra:quote f) " --version") T))
        (princ "\nWARNING: the selected program did not run correctly.")
        (princ "\nEngine check OK."))))
  (princ))

(defun c:ARCHVECTRA (/ pdf page scl out dxf pt)
  (setq pdf (getfiled "ArchVectra - select a PDF plan" (getvar "DWGPREFIX") "pdf" 0))
  (if pdf
    (progn
      (initget 6)
      (setq page (getint "\nPage number <1>: "))
      (if (null page) (setq page 1))
      (initget 4)
      (setq scl (getreal "\nDrawing scale 1:N - enter N (0 = unknown) <100>: "))
      (if (null scl) (setq scl 100.0))
      (if (= scl 0) (setq scl nil))
      (if (setq out (archvectra:run-engine pdf page scl))
        (if (setq dxf (archvectra:result-dxf pdf out))
          (progn
            (setq pt (getpoint "\nInsertion point <0,0>: "))
            (if (null pt) (setq pt '(0.0 0.0 0.0)))
            (if (archvectra:insert dxf pt 1.0 0.0)
              (progn
                (if (null scl)
                  (princ "\nNOTE: no scale given - geometry is in sheet millimetres, NOT real-world size."))
                (command "_.ZOOM" "_E")
                (archvectra:after-import out))))
          (princ (strcat "\nNo DXF produced - see " out "\\run.log"))))))
  (princ))

(defun c:ARCHVECTRA-UNDERLAY (/ sel ed def pdf page ins rot out dxf pg bb minp maxp w k)
  ;; Experimental: align the result with an attached PDF underlay (PDFATTACH).
  (setq sel (entsel "\nSelect an attached PDF underlay: "))
  (cond
    ((null sel) nil)
    ((/= (cdr (assoc 0 (setq ed (entget (car sel))))) "PDFUNDERLAY")
     (princ "\nThat is not a PDF underlay."))
    (T
     (setq def  (entget (cdr (assoc 340 ed)))
           pdf  (findfile (cdr (assoc 1 def)))
           page (if (assoc 2 def) (atoi (cdr (assoc 2 def))) 1)
           ins  (cdr (assoc 10 ed))
           rot  (cdr (assoc 50 ed)))
     (if (or (null page) (< page 1)) (setq page 1))
     (if (null rot) (setq rot 0.0))
     (cond
       ((null pdf) (princ (strcat "\nCannot find the PDF file: " (cdr (assoc 1 def)))))
       ((setq out (archvectra:run-engine pdf page nil))   ; sheet mm, page origin = lower-left
        (setq dxf (archvectra:result-dxf pdf out)
              pg  (archvectra:page-mm out))
        ;; scale = underlay width in drawing units / sheet width in mm (unrotated bounding box)
        (vla-getboundingbox (vlax-ename->vla-object (car sel)) 'minp 'maxp)
        (setq bb (list (vlax-safearray->list minp) (vlax-safearray->list maxp))
              w  (- (car (cadr bb)) (car (car bb))))
        (if (and pg (> (car pg) 0) (equal rot 0.0 1e-9))
          (setq k (/ w (car pg)))
          (progn
            (setq k (cdr (assoc 41 ed)))
            (princ "\nNOTE: rotated underlay - using its scale factor; check the alignment visually.")))
        (if (and dxf (archvectra:insert dxf ins k (* 180.0 (/ rot pi))))
          (progn
            (princ (strcat "\nPlaced over the underlay (scale factor " (rtos k 2 6)
                           "). Geometry is aligned to the sheet; check one known dimension with ARCHVECTRA-CHECKDIM."))
            (princ "\nNOTE: a clipped underlay makes the automatic scale wrong - unclip it first.")
            (archvectra:after-import out)))))))
  (princ))

(defun c:ARCHVECTRA-REPORT (/ out f)
  (setq out *archvectra-last-out*)
  (if (null out)
    (princ "\nNo ArchVectra run in this session.")
    (progn
      (setq f (car (vl-directory-files (strcat out "\\02_vector") "*_review.pdf" 1)))
      (cond
        (f (archvectra:open-file (strcat out "\\02_vector\\" f)))
        ((findfile (strcat out "\\03_validation\\report.md"))
         (archvectra:open-file (strcat out "\\03_validation\\report.md")))
        (T (princ (strcat "\nNothing to open in " out))))))
  (princ))

;;; ================================================================ xdata helpers
(defun archvectra:xdata (ename / ed xd)
  ;; returns the ARCHVECTRA xdata list ((1000 . "kind=...") (1000 . "confidence") (1040 . 0.9) ...)
  (setq ed (entget ename '("ARCHVECTRA")))
  (if (setq xd (assoc -3 ed)) (cdr (cadr xd)) nil))

(defun archvectra:number-after (key xd / found val)
  ;; value of a (1000 . key) (1040 . value) pair
  (while (and xd (not found))
    (if (and (= (caar xd) 1000) (= (cdar xd) key) (cadr xd) (= (car (cadr xd)) 1040))
      (setq found T val (cdr (cadr xd))))
    (setq xd (cdr xd)))
  val)

(defun archvectra:string-value (prefix xd / val s)
  ;; value of a (1000 . "prefix=value") tag
  (foreach pair xd
    (if (and (= (car pair) 1000)
             (setq s (cdr pair))
             (wcmatch s (strcat prefix "=*")))
      (setq val (substr s (+ 2 (strlen prefix))))))
  val)

;;; ================================================================ utility commands
(defun c:ARCHVECTRA-IMPORT (/ f pt)
  (setq f (getfiled "ArchVectra DXF" "" "dxf" 0))
  (if f
    (progn
      (setq pt (getpoint "\nInsertion point <0,0>: "))
      (if (null pt) (setq pt '(0.0 0.0 0.0)))
      (if (archvectra:insert f pt 1.0 0.0)
        (progn
          (command "_.ZOOM" "_E")
          (princ (strcat "\nImported " f
                         "\nUnits: real-world mm only if a scale was given (header variable ARCHVECTRA_UNITS)."))))))
  (princ))

(defun c:ARCHVECTRA-LAYERS (/ name lay layers)
  (setq layers (vla-get-layers (vla-get-activedocument (vlax-get-acad-object))))
  (foreach spec *archvectra-layers*
    (setq name (car spec))
    (if (tblsearch "LAYER" name)
      (progn
        (setq lay (vla-item layers name))
        (vla-put-color lay (cadr spec))
        (vla-put-lineweight lay (caddr spec))
        (vla-put-plottable lay (if (cadddr spec) :vlax-true :vlax-false)))))
  (princ "\nArchVectra layer standards applied (reference layers set to no-plot).")
  (princ))

(defun c:ARCHVECTRA-REVIEW (/ ss i e c xd msg sev ans)
  (setq ss (ssget "_X" '((0 . "CIRCLE") (8 . "Z-REVIEW"))))
  (if (not ss)
    (princ "\nNo review flags.")
    (progn
      (setq i 0 ans "Next")
      (while (and (< i (sslength ss)) (/= ans "eXit"))
        (setq e (ssname ss i))
        (if (entget e)
          (progn
            (setq c   (cdr (assoc 10 (entget e)))
                  xd  (archvectra:xdata e)
                  msg (archvectra:string-value "message" xd)
                  sev (archvectra:string-value "severity" xd))
            (command "_.ZOOM" "_C" c (* 40.0 (cdr (assoc 40 (entget e)))))
            (princ (strcat "\n[" (itoa (1+ i)) "/" (itoa (sslength ss)) "] "
                           (if sev sev "?") ": " (if msg msg "")))
            (initget "Next Delete eXit")
            (setq ans (getkword "\n[Next/Delete flag/eXit] <Next>: "))
            (if (null ans) (setq ans "Next"))
            (if (= ans "Delete") (entdel e))))
        (setq i (1+ i)))))
  (princ))

(defun c:ARCHVECTRA-LOWCONF (/ thr ss out i e conf)
  (setq thr (getreal "\nConfidence threshold <0.7>: "))
  (if (null thr) (setq thr 0.7))
  (setq ss (ssget "_X" '((-3 ("ARCHVECTRA")))) out (ssadd) i 0)
  (if ss
    (repeat (sslength ss)
      (setq e (ssname ss i)
            conf (archvectra:number-after "confidence" (archvectra:xdata e)))
      (if (and conf (< conf thr)) (ssadd e out))
      (setq i (1+ i))))
  (princ (strcat "\n" (itoa (sslength out)) " entities below " (rtos thr 2 2)
                 " - they are now the active selection."))
  (sssetfirst nil out)
  (princ))

(defun c:ARCHVECTRA-WALLS (/ ss i e ed thk len)
  (setq ss (ssget "_X" '((0 . "LINE") (8 . "A-WALL-CNTR"))) i 0)
  (if ss
    (repeat (sslength ss)
      (setq e (ssname ss i) ed (entget e)
            thk (archvectra:number-after "thickness" (archvectra:xdata e))
            len (distance (cdr (assoc 10 ed)) (cdr (assoc 11 ed))))
      (princ (strcat "\nwall " (itoa (1+ i)) ": length " (rtos len 2 1)
                     "  thickness " (if thk (rtos thk 2 1) "?")))
      (setq i (1+ i)))
    (princ "\nNo wall centrelines (layer A-WALL-CNTR)."))
  (princ))

(defun c:ARCHVECTRA-CHECKDIM (/ p1 p2 d expect tol)
  (setq p1 (getpoint "\nFirst point: "))
  (if p1 (setq p2 (getpoint p1 "\nSecond point: ")))
  (if (and p1 p2)
    (progn
      (setq d (distance p1 p2)
            expect (getreal (strcat "\nMeasured " (rtos d 2 2) ". Expected value: ")))
      (if (and expect (> expect 0))
        (progn
          (setq tol (abs (- d expect)))
          (princ (strcat "\nDifference " (rtos tol 2 2) " ("
                         (rtos (* 100.0 (/ tol expect)) 2 2) "%)."))
          (if (> (/ tol expect) 0.01)
            (princ "\nWARNING: more than 1% off - check the scale (try --known-distance)."))))))
  (princ))

(defun c:ARCHVECTRA-CLEAN (/ ss)
  ;; OVERKILL is a standard command since AutoCAD 2012 (Express Tools before that).
  (setq ss (ssget "_X" '((8 . "A-DETL,A-DETL-ARC,A-DOOR,A-GLAZ"))))
  (if ss
    (command "_.-OVERKILL" ss "" "")
    (princ "\nNothing to clean."))
  (princ))

(princ "\nArchVectra loaded. Commands: ARCHVECTRA, ARCHVECTRA-UNDERLAY, ARCHVECTRA-SETUP, -REVIEW, -REPORT, -LOWCONF, -WALLS, -CHECKDIM, -IMPORT, -LAYERS, -CLEAN")
(princ)
