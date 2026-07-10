       IDENTIFICATION DIVISION.
       PROGRAM-ID. DEADEX.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM LIVE-PARA.
           GOBACK.
       LIVE-PARA.
           DISPLAY 'LIVE'.
           EXIT.
       DEAD-A.
           PERFORM DEAD-B.
           EXIT.
       DEAD-B.
           PERFORM DEAD-A.
           EXIT.
