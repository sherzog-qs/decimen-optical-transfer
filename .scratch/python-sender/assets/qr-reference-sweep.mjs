import QRCode from "qrcode";
const sizes = [200, 500, 1000, 1465, 1850, 2331, 2953];
const eccs = ["L", "M", "Q", "H"];
function frameBytes(n){const b=new Uint8Array(n);for(let i=0;i<n;i++)b[i]=(i*37+11)&0xff;b[0]=0xd1;b[1]=0xc3;b[2]=3;b[3]=0;return b;}
const out={};
for(const n of sizes) for(const ecc of eccs){
  let qr; try{ qr=QRCode.create([{data:frameBytes(n),mode:"byte"}],{errorCorrectionLevel:ecc,maskPattern:4}); }catch(e){ continue; }
  const bits=qr.modules.data; let hex="";
  for(let i=0;i<bits.length;i+=8){let v=0;for(let j=0;j<8&&i+j<bits.length;j++)v|=(bits[i+j]?1:0)<<(7-j);hex+=v.toString(16).padStart(2,"0");}
  out[`${n}${ecc}`]={version:qr.version,size:qr.modules.size,hex};
}
console.log(JSON.stringify(out));
