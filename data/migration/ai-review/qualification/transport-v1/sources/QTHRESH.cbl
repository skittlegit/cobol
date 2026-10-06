       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTHRESH.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-VALUE PIC 9(3) VALUE ZERO.
       01 WS-FLAG PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           STOP RUN.
       2000-CHECK.
           IF WS-VALUE > 90
               MOVE 'Y' TO WS-FLAG
           ELSE
               MOVE 'N' TO WS-FLAG
           END-IF.
