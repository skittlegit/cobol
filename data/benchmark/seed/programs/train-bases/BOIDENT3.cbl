       IDENTIFICATION DIVISION.
       PROGRAM-ID. BOIDENT3.
      * BO IDENTIFICATION - ENTITY-TYPE BRANCHED THRESHOLDS
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-ENTITY-TYPE            PIC X(1) VALUE SPACE.
       01  WS-OWN-PCT                PIC 9(3)V99 VALUE ZERO.
       01  WS-CTRL-IND               PIC X(1) VALUE 'N'.
       01  WS-IS-BO                  PIC X(1) VALUE 'N'.
       01  WS-PAGE-NBR               PIC 9(6) VALUE ZERO.
       01  WS-PRINT-AREA.
           05  WS-PRINT-LINE OCCURS 6 PIC X(26).
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-ENTITY-TYPE
           ACCEPT WS-OWN-PCT
           ACCEPT WS-CTRL-IND
           PERFORM 2000-CLASSIFY
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
       2000-CLASSIFY.
           EVALUATE WS-ENTITY-TYPE
             WHEN 'C'
               IF WS-OWN-PCT > 10.00 MOVE 'Y' TO WS-IS-BO END-IF
             WHEN 'P'
               IF WS-OWN-PCT > 10.00 OR WS-CTRL-IND = 'Y'
                  MOVE 'Y' TO WS-IS-BO
               END-IF
             WHEN OTHER
               IF WS-OWN-PCT > 15.00 MOVE 'Y' TO WS-IS-BO END-IF
           END-EVALUATE.
