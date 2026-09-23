       IDENTIFICATION DIVISION.
       PROGRAM-ID. T6BO01.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PARTNER.
           05  WS-CAPITAL-PCT        PIC 9(3)V99 VALUE ZERO.
           05  WS-IS-BO              PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CAPITAL-PCT
           PERFORM 2000-IDENTIFY-OWNER
           DISPLAY WS-IS-BO
           STOP RUN.
       2000-IDENTIFY-OWNER.
           IF WS-CAPITAL-PCT > 15
              MOVE 'Y' TO WS-IS-BO
           ELSE
              MOVE 'N' TO WS-IS-BO
           END-IF.
