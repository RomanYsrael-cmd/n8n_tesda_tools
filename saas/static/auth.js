import {initializeApp} from 'https://www.gstatic.com/firebasejs/11.1.0/firebase-app.js';
import {getAuth,signInWithEmailAndPassword,createUserWithEmailAndPassword,sendEmailVerification} from 'https://www.gstatic.com/firebasejs/11.1.0/firebase-auth.js';

const form=document.querySelector('#login-form');
const error=document.querySelector('#auth-error');
const success=document.querySelector('#auth-success');
const auth=getAuth(initializeApp({apiKey:form.dataset.apiKey,projectId:form.dataset.projectId,authDomain:`${form.dataset.projectId}.firebaseapp.com`}));

form.addEventListener('submit',async event=>{
  event.preventDefault(); const button=form.querySelector('button[type="submit"]');
  button.disabled=true; button.textContent='Signing in…'; error.hidden=true;
  try{
    const result=await signInWithEmailAndPassword(auth,document.querySelector('#email').value,document.querySelector('#password').value);
    const response=await fetch('/auth/session',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({idToken:await result.user.getIdToken()})});
    if(!response.ok)throw new Error((await response.json()).detail||'Sign-in failed'); location.href='/app';
  }catch(ex){error.textContent=ex.message;error.hidden=false;button.disabled=false;button.textContent='Sign in';}
});

document.querySelector('#create-account').addEventListener('click',async event=>{
  const button=event.currentTarget; button.disabled=true; error.hidden=true; success.hidden=true;
  try{
    const result=await createUserWithEmailAndPassword(auth,document.querySelector('#email').value,document.querySelector('#password').value);
    await sendEmailVerification(result.user); success.textContent='Account created. Check your inbox and verify your email, then sign in.'; success.hidden=false;
  }catch(ex){error.textContent=ex.message;error.hidden=false;}finally{button.disabled=false;}
});
