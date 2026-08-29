       IDENTIFICATION DIVISION.
       PROGRAM-ID. T6V2P4A.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-OWNERSHIP-BASIS       PIC X VALUE 'C'.
       01  WS-CAPITAL-PCT           PIC 9(3)V99 VALUE ZERO.
       01  WS-PROFIT-PCT            PIC 9(3)V99 VALUE ZERO.
       01  WS-IS-BO                 PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-OWNERSHIP-BASIS
           ACCEPT WS-CAPITAL-PCT
           ACCEPT WS-PROFIT-PCT
           PERFORM 2000-IDENTIFY-OWNER
           DISPLAY WS-IS-BO
           STOP RUN.
       2000-IDENTIFY-OWNER.
           IF WS-OWNERSHIP-BASIS = 'C'
              IF WS-CAPITAL-PCT > 15
                 MOVE 'Y' TO WS-IS-BO
              END-IF
           ELSE
              IF WS-PROFIT-PCT > 15
                 MOVE 'Y' TO WS-IS-BO
              END-IF
           END-IF.
