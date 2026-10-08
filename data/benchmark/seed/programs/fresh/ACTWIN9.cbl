       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACTWIN9.
      * NEW CARD ACTIVATION FOLLOW-UP (OTP CONSENT, THEN CLOSE)
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CARD-STATUS            PIC X(1) VALUE 'I'.
           88  CARD-ACTIVE           VALUE 'A'.
       01  WS-ISSUE-AGE              PIC 9(4) VALUE ZERO.
       01  WS-OTP-AGE                PIC 9(4) VALUE ZERO.
       01  WS-NEXT-STEP              PIC X(10) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CARD-STATUS
           ACCEPT WS-ISSUE-AGE
           ACCEPT WS-OTP-AGE
           PERFORM 2000-NEXT-STEP
           DISPLAY 'STEP: ' WS-NEXT-STEP
           STOP RUN.
       2000-NEXT-STEP.
           IF CARD-ACTIVE
              MOVE 'NONE' TO WS-NEXT-STEP
           ELSE
              IF WS-ISSUE-AGE > 30
                 IF WS-OTP-AGE > 7
                    MOVE 'CLOSECARD' TO WS-NEXT-STEP
                 ELSE
                    MOVE 'ASKCONSENT' TO WS-NEXT-STEP
                 END-IF
              ELSE
                 MOVE 'WAIT' TO WS-NEXT-STEP
              END-IF
           END-IF.
