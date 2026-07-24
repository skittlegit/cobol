       IDENTIFICATION DIVISION.
       PROGRAM-ID. DEADISO.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY 'MAIN'.
           GOBACK.
      * ISO-PARA is isolated: no PERFORM/GO TO/CALL into it, and MAIN-PARA's
      * GOBACK stops any fall-through. It is a forest root and unreachable.
       ISO-PARA.
           DISPLAY 'DEAD'.
           GOBACK.
