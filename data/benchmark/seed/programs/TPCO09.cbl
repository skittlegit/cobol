       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPCO09.
      * COMPANY BO - DIRECT PLUS INDIRECT HOLDING
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-DIRECT-PCT             PIC 9(3)V99 VALUE ZERO.
       01  WS-INDIRECT-PCT           PIC 9(3)V99 VALUE ZERO.
       01  WS-EFFECTIVE-PCT          PIC 9(3)V99 VALUE ZERO.
       01  WS-CONTROL-OTHER          PIC X VALUE 'N'.
       01  WS-IS-BO                  PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-DIRECT-PCT
           ACCEPT WS-INDIRECT-PCT
           ACCEPT WS-CONTROL-OTHER
           COMPUTE WS-EFFECTIVE-PCT = WS-DIRECT-PCT + WS-INDIRECT-PCT
           PERFORM 2000-TEST
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
       2000-TEST.
           IF WS-EFFECTIVE-PCT > 25.00
              MOVE 'Y' TO WS-IS-BO
           ELSE
              IF WS-CONTROL-OTHER = 'Y'
                 MOVE 'Y' TO WS-IS-BO
              ELSE
                 MOVE 'N' TO WS-IS-BO
              END-IF
           END-IF.
