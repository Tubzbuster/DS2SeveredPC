#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
long refpack_decompress(const uint8_t*, long, uint8_t*, long);
void xas_encode(const int16_t*, int, uint8_t*);
static uint32_t rs=12345; static uint32_t rnd(void){rs^=rs<<13;rs^=rs>>17;rs^=rs<<5;return rs;}
int main(int argc,char**argv){
  FILE*f=fopen(argv[1],"rb"); fseek(f,0,2); long L=ftell(f); fseek(f,0,0);
  uint8_t*b=malloc(L); fread(b,1,L,f); fclose(f);
  long p=0,n=0,ok=0,fz=0,fzrej=0;
  while(p<L){uint32_t s,u; memcpy(&s,b+p,4); memcpy(&u,b+p+4,4); p+=8;
    uint8_t*src=malloc(s); memcpy(src,b+p,s); uint8_t*ref=b+p+s; p+=s+u;
    uint8_t*dst=malloc(u?u:1);
    long g=refpack_decompress(src,s,dst,u); n++; if(g==(long)u&&!memcmp(dst,ref,u))ok++;
    /* fuzz: truncations and byte flips, exact-size heap buffers so ASan sees any overrun */
    for(int t=0;t<20;t++){ long ss = t<10 ? (long)(rnd()%(s+1)) : (long)s;
      uint8_t*m=malloc(ss?ss:1); memcpy(m,src,ss);
      if(t>=10) for(int k=0;k<4;k++) if(ss) m[rnd()%ss]^=1<<(rnd()%8);
      long cap = t%3==0 ? (long)(rnd()%(u+1)) : (long)u;
      uint8_t*d=malloc(cap?cap:1); long r=refpack_decompress(m,ss,d,cap); fz++; if(r<0)fzrej++;
      if(r>cap){printf("BAD: wrote %ld > cap %ld\n",r,cap);return 1;}
      free(m); free(d);}
    free(src); free(dst);}
  /* header-only inputs of every length 0..12 with every flag combo */
  for(int fl=0;fl<256;fl++) for(int ln=0;ln<=12;ln++){uint8_t*m=malloc(ln?ln:1); for(int k=0;k<ln;k++)m[k]=rnd(); if(ln>0)m[0]=fl; if(ln>1)m[1]=0xFB; uint8_t d[64]; refpack_decompress(m,ln,d,64); free(m);}
  /* xas: random and edge-value audio */
  for(int t=0;t<200;t++){int nf=1+rnd()%40; int16_t*x=malloc(nf*128*2); for(int i=0;i<nf*128;i++) x[i]= t%3==0 ? (rnd()&1?32767:-32768) : (int16_t)rnd();
    uint8_t*o=malloc(nf*0x4C); xas_encode(x,nf,o); free(x); free(o);}
  printf("refpack %ld/%ld exact; fuzz %ld runs, %ld rejected; xas ok\n",ok,n,fz,fzrej); free(b); return ok==n?0:1;}
