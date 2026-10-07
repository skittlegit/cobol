       IDENTIFICATION DIVISION.
       PROGRAM-ID. CKYUP9.
      * CENTRAL KYC REGISTRY UPLOAD TRACKER
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-UPDATE-DAY             PIC 9(5) VALUE ZERO.
       01  WS-RUN-DAY                PIC 9(5) VALUE ZERO.
       01  WS-ELAPSED                PIC S9(5) VALUE ZERO.
       01  WS-UPLOADED               PIC X(1) VALUE 'N'.
       01  WS-UPL-STATUS             PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-UPDATE-DAY
           ACCEPT WS-RUN-DAY
           ACCEPT WS-UPLOADED
           PERFORM 2000-CHECK-UPLOAD
           DISPLAY 'UPLOAD: ' WS-UPL-STATUS
           STOP RUN.
       2000-CHECK-UPLOAD.
           COMPUTE WS-ELAPSED = WS-RUN-DAY - WS-UPDATE-DAY
           IF WS-UPLOADED = 'Y'
              MOVE 'DONE' TO WS-UPL-STATUS
           ELSE
              IF WS-ELAPSED > 7
                 MOVE 'LATE' TO WS-UPL-STATUS
              ELSE
                 MOVE 'PENDING' TO WS-UPL-STATUS
              END-IF
           END-IF.
