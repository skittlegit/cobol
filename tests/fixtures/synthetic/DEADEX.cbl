       IDENTIFICATION DIVISION.
       PROGRAM-ID. DEADEX.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM LIVE-PARA.
           GOBACK.
      * LIVE-PARA ends in GOBACK: the fall-through barrier that keeps the
      * DEAD-A/DEAD-B cycle below from being fallen into (F7/T1.2b).
       LIVE-PARA.
           DISPLAY 'LIVE'.
           GOBACK.
       DEAD-A.
           PERFORM DEAD-B.
           EXIT.
       DEAD-B.
           PERFORM DEAD-A.
           EXIT.
