       IDENTIFICATION DIVISION.
       PROGRAM-ID. OVDCHK1.
      *----------------------------------------------------------------
      * KYC ONBOARDING - ACCEPT ONLY OFFICIALLY VALID DOCUMENTS (OVD).
      * THE PRESENTED DOCUMENT CODE IS SCREENED AGAINST THE SHARED OVD
      * REGISTRY BEFORE THE ACCOUNT MAY BE OPENED.
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY OVDLIST.
       01  WS-KYC-DECISION PIC X(6) VALUE 'REJECT'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-OVD-CODE
           PERFORM 2000-SCREEN-OVD
           DISPLAY 'KYC: ' WS-KYC-DECISION
           STOP RUN.
       2000-SCREEN-OVD.
           IF ACCEPTED-OVD
              MOVE 'ACCEPT' TO WS-KYC-DECISION
           ELSE
              MOVE 'REJECT' TO WS-KYC-DECISION
           END-IF.
