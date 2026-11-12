;;; archvectra.lsp - AutoCAD helpers for DXF files produced by archvectra
;;;
;;; Load with APPLOAD (or (load "archvectra.lsp")), then use the commands below.
;;; The computer-vision work is done in Python; these commands only organise,
;;; inspect and check the imported geometry.
;;;
;;; NOTE: written against documented AutoLISP / Visual LISP functions but NOT
;;; executed in AutoCAD by the author of this file - test before production use.
;;;
;;; Commands
;;;   ARCHVECTRA-IMPORT     insert an archvectra DXF as an exploded block at 0,0
;;;   ARCHVECTRA-LAYERS     apply colours / lineweights / plot flags to archvectra layers
;;;   ARCHVECTRA-REVIEW     step through Z-REVIEW flags (zoom to each, show message)
;;;   ARCHVECTRA-LOWCONF    select entities whose ARCHVECTRA confidence is below a threshold
;;;   ARCHVECTRA-WALLS      list wall centrelines with measured thickness
;;;   ARCHVECTRA-CHECKDIM   compare a picked distance with an expected value
;;;   ARCHVECTRA-CLEAN      run OVERKILL on linework layers (duplicates / overlaps)

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

;;; ------------------------------------------------------------ helpers
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

;;; ------------------------------------------------------------ commands
(defun c:ARCHVECTRA-IMPORT (/ f)
  (setq f (getfiled "archvectra DXF" "" "dxf" 0))
  (if f
    (progn
      (command "_.-INSERT" (strcat "*" f) "0,0" "1" "0")
      (c:ARCHVECTRA-LAYERS)
      (command "_.ZOOM" "_E")
      (princ (strcat "\nImported " f
                     "\nCheck the drawing units: archvectra writes real-world mm only when"
                     " the scale was calibrated (header variable ARCHVECTRA_UNITS).")))
    (princ "\nCancelled."))
  (princ))

(defun c:ARCHVECTRA-LAYERS (/ name lay)
  (foreach spec *archvectra-layers*
    (setq name (car spec))
    (if (tblsearch "LAYER" name)
      (progn
        (command "_.-LAYER" "_C" (itoa (cadr spec)) name
                 "_LW" (rtos (/ (caddr spec) 100.0) 2 2) name "")
        (setq lay (vla-item (vla-get-layers (vla-get-activedocument (vlax-get-acad-object))) name))
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
        (setq e (ssname ss i)
              c (cdr (assoc 10 (entget e)))
              xd (archvectra:xdata e)
              msg (archvectra:string-value "message" xd)
              sev (archvectra:string-value "severity" xd))
        (command "_.ZOOM" "_C" c (* 40.0 (cdr (assoc 40 (entget e)))))
        (princ (strcat "\n[" (itoa (1+ i)) "/" (itoa (sslength ss)) "] "
                       (if sev sev "?") ": " (if msg msg "")))
        (initget "Next Delete eXit")
        (setq ans (getkword "\n[Next/Delete flag/eXit] <Next>: "))
        (if (null ans) (setq ans "Next"))
        (if (= ans "Delete") (entdel e))
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
                 " - they are now the active selection (use PSELECT/Properties)."))
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
  (setq p1 (getpoint "\nFirst point: ")
        p2 (getpoint p1 "\nSecond point: "))
  (if (and p1 p2)
    (progn
      (setq d (distance p1 p2)
            expect (getreal (strcat "\nMeasured " (rtos d 2 2) ". Expected value: ")))
      (if expect
        (progn
          (setq tol (abs (- d expect)))
          (princ (strcat "\nDifference " (rtos tol 2 2) " ("
                         (rtos (* 100.0 (/ tol expect)) 2 2) "%)."))
          (if (> (/ tol expect) 0.01)
            (princ "\nWARNING: more than 1% off - check scale calibration."))))))
  (princ))

(defun c:ARCHVECTRA-CLEAN (/ ss)
  ;; OVERKILL is a standard command since AutoCAD 2012 (Express Tools before that).
  (setq ss (ssget "_X" '((8 . "A-DETL,A-DETL-ARC,A-DOOR,A-GLAZ"))))
  (if ss
    (command "_.-OVERKILL" ss "" "")
    (princ "\nNothing to clean."))
  (princ))

(princ "\narchvectra.lsp loaded: ARCHVECTRA-IMPORT, -LAYERS, -REVIEW, -LOWCONF, -WALLS, -CHECKDIM, -CLEAN")
(princ)
