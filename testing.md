# MoHChat UAT Test Guide (Upload-Only)

## 1. Purpose
This guide is for validating MoHChat in Moodle using upload-only testing (no scope validation).

## 2. Test Accounts
1. Admin account  
Username: `admin`  
Password: `@Admin123`

2. Student account  
Username: `demouser`  
Password: `demouser`

## 3. Tester Onboarding (WhatsApp)
To join testers on WhatsApp, send this message:

`join company-tears`

Send to: `+1 (415) 523-8886`

## 4. Preconditions
1. MoHChat plugin is installed and enabled.
2. FastAPI backend is running and connected.
3. At least one Moodle course exists.
4. At least one PDF file is ready for upload.

## 5. Admin Test Cases

### TC-ADM-01: Login
Steps:
1. Go to Moodle login page.
2. Log in with admin credentials.

Expected result:
1. Admin successfully logs in.

### TC-ADM-02: Add MoHChat activity
Steps:
1. Open target course.
2. Turn Edit mode on.
3. Click Add activity/resource.
4. Select MoHChat.
5. Enter activity name.
6. Save and display.

Expected result:
1. Activity is created and opens without errors.

### TC-ADM-03: Upload document
Steps:
1. In MoHChat activity, go to Teacher/Admin tools.
2. Upload one PDF document.
3. Wait for completion message.

Expected result:
1. Upload succeeds.
2. Document appears in Indexed Documents list.

### TC-ADM-04: Chat from uploaded document
Steps:
1. Ask a question that is answered by the uploaded PDF.
2. Submit question.

Expected result:
1. Chat returns a relevant answer from uploaded content.
2. Supporting reference is shown.

### TC-ADM-05: Open supporting reference
Steps:
1. Click a supporting reference in the chat response.

Expected result:
1. Document opens in viewer.
2. Admin can read the referenced material.

### TC-ADM-06: Delete indexed document
Steps:
1. In Indexed Documents list, click Delete on a document.
2. Confirm delete action.

Expected result:
1. Document is removed from index list.
2. Deleted document is no longer available for chat retrieval.

## 6. Student Test Cases

### TC-STU-01: Login
Steps:
1. Log out from admin.
2. Log in with student account.

Expected result:
1. Student successfully logs in.

### TC-STU-02: Access MoHChat
Steps:
1. Open the course.
2. Open the MoHChat activity.

Expected result:
1. Student can access chat page.

### TC-STU-03: Permissions check
Steps:
1. Review visible UI controls.

Expected result:
1. Student sees chat interface.
2. Student does not see admin tools (upload/sync/delete/index management).

### TC-STU-04: Chat with uploaded content
Steps:
1. Ask a question from uploaded document content.
2. Ask a question not covered by uploaded documents.

Expected result:
1. In-scope question returns relevant answer.
2. Out-of-scope question returns fallback response indicating answer not found in indexed docs.

## 7. UAT Pass/Fail Criteria
1. PASS if all critical tests succeed without blocking errors.
2. FAIL if upload, chat, reference viewing, or role permissions are broken.

## 8. Defect Log Template
1. Defect ID:
2. Role used:
3. Test case ID:
4. Steps to reproduce:
5. Expected result:
6. Actual result:
7. Screenshot:
8. Browser/device:
9. Severity:
10. Reported by/date:

## 9. Printable Checklist

Date: __________  
Tester: __________  
Environment: __________  

[ ] Admin login works  
[ ] Student login works  
[ ] MoHChat activity can be added  
[ ] Activity opens with no errors  
[ ] PDF upload works  
[ ] Uploaded doc appears in index list  
[ ] Chat answers from uploaded doc  
[ ] Supporting reference appears  
[ ] Reference opens in viewer  
[ ] Admin can delete indexed doc  
[ ] Student sees chat only  
[ ] Student cannot upload/delete/manage docs  
[ ] Out-of-scope question gives fallback response  

Final Result: PASS / FAIL

Notes:  
__________________________________________________  
__________________________________________________  
__________________________________________________

