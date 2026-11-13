package io.micor.prp.health;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.cert.CertificateFactory;
import java.util.*;
import javax.net.ssl.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.keycloak.models.*;
import org.keycloak.protocol.oauth2.cimd.clientpolicy.executor.*;
import org.keycloak.protocol.oauth2.cimd.provider.ClientIdMetadataDocumentProvider;
import org.keycloak.representations.oidc.OIDCClientRepresentation;
import org.keycloak.services.clientpolicy.*;
import org.keycloak.services.clientpolicy.context.*;
import org.keycloak.util.JsonSerialization;

/** Reviewed ChatGPT CIMD compatibility; real public TLS through a fixed-destination CONNECT broker. */
public class HealthCimdMetadata extends ClientIdMetadataDocumentExecutor {
 static final String ID="https://chatgpt.com/oauth/client.json", JWKS="https://chatgpt.com/oauth/jwks.json";
 static final String REDIRECT="https://chatgpt.com/connector_platform_oauth_redirect";
 public HealthCimdMetadata(KeycloakSession s,ClientIdMetadataDocumentExecutorFactoryProviderConfig c){super(s,c);}
 public String getProviderId(){return "prp-health-cimd-metadata";}
 static ClientPolicyException reject(String code){return new ClientPolicyException("invalid_request","PRP_CIMD_"+code);}
 static void require(boolean b,String code)throws ClientPolicyException{if(!b)throw reject(code);}
 @Override protected OIDCClientRepresentationWithCacheControl fetchClientMetadata(URI id,boolean update,ClientIdMetadataDocumentProvider provider)throws ClientPolicyException{
  require(session.getContext().getRealm()!=null && "prp-mcp-prod".equals(session.getContext().getRealm().getName()),"REALM");
  require(ID.equals(id.toString()),"METADATA_URL");
  try{
   OIDCClientRepresentation dto=normalize(fetch(ID),fetch(JWKS));
   augmentClientOIDC(dto); // Retain built-in verification/validation/create hooks.
   return new OIDCClientRepresentationWithCacheControl(dto,new ClientMetadataCacheControl("max-age=30",0,30));
  }catch(ClientPolicyException e){throw e;}catch(Exception e){throw reject("STRICT_METADATA_OR_TRANSPORT");}
 }
 static OIDCClientRepresentation normalize(byte[] metadata,byte[] jwks)throws Exception{
   // Fetch and validate known choices BEFORE the native strict DTO conversion.
   JsonNode root=JsonSerialization.mapper.reader().with(com.fasterxml.jackson.core.JsonParser.Feature.STRICT_DUPLICATE_DETECTION).readTree(metadata);
   require(root.isObject(),"METADATA_OBJECT");
   ObjectNode n=(ObjectNode)root;
   require(ID.equals(n.path("client_id").asText()),"METADATA_ID");
   require("https://chatgpt.com/".equals(n.path("client_uri").asText()),"CLIENT_URI");
   require("https://persistent.oaistatic.com/sonic/misc/openai-logo.png".equals(n.path("logo_uri").asText()),"LOGO_URI");
   require(!n.has("tos_uri")&&!n.has("policy_uri"),"UNREVIEWED_URI");
   require(n.path("redirect_uris").isArray()&&n.path("redirect_uris").size()==1&&REDIRECT.equals(n.path("redirect_uris").get(0).asText()),"METADATA_REDIRECT");
   // RP Metadata Choices may omit the singular method. Reject conflicting explicit values.
   if(n.has("token_endpoint_auth_method"))
    require(n.get("token_endpoint_auth_method").isTextual() && "private_key_jwt".equals(n.get("token_endpoint_auth_method").asText()),"METHOD");
   JsonNode choices=n.get("token_endpoint_auth_methods_supported");
   require(choices!=null&&choices.isArray()&&choices.size()>0&&choices.size()<=2,"CHOICES");
   Set<String> methods=new HashSet<>();
   for(JsonNode x:choices){require(x.isTextual()&&Set.of("none","private_key_jwt").contains(x.asText())&&methods.add(x.asText()),"CHOICES");}
   require(methods.contains("private_key_jwt"),"CHOICES");
   // Materialize the selected method before Keycloak\'s strict native DTO parse.
   n.put("token_endpoint_auth_method","private_key_jwt");
   require(JWKS.equals(n.path("jwks_uri").asText())&&!n.has("jwks"),"JWKS_URL");
   // Preflight the SAME pinned JWKS source. Native client-jwt verification still runs.
   JsonNode keys=JsonSerialization.mapper.reader().with(com.fasterxml.jackson.core.JsonParser.Feature.STRICT_DUPLICATE_DETECTION).readTree(jwks).path("keys");
   require(keys.isArray()&&keys.size()>0&&keys.size()<=4,"JWKS");
   for(JsonNode k:keys){require("RSA".equals(k.path("kty").asText())&&k.hasNonNull("kid")&&k.hasNonNull("n")&&k.hasNonNull("e"),"JWKS_KEY");
    for(String privateField:List.of("d","p","q","dp","dq","qi","k"))require(!k.has(privateField),"PRIVATE_JWK");}
   n.remove("token_endpoint_auth_methods_supported"); // ONLY this known extension is consumed.
   return JsonSerialization.readValue(n.toString(),OIDCClientRepresentation.class);
 }
 static byte[] fetch(String url)throws Exception{
  if(!Set.of(ID,JWKS).contains(url))throw new IOException("URL");
  long deadline=System.nanoTime()+java.time.Duration.ofSeconds(10).toNanos();
  try(Socket raw=new Socket()){
   raw.connect(new InetSocketAddress("egress",3128),2000);raw.setSoTimeout(6000);
   raw.getOutputStream().write("CONNECT chatgpt.com:443 HTTP/1.1\r\nHost: chatgpt.com:443\r\n\r\n".getBytes(StandardCharsets.US_ASCII));
   String connect=readHeader(raw.getInputStream(),4096,deadline);
   if(!connect.startsWith("HTTP/1.1 200 "))throw new IOException("PROXY");
   // Real system/public trust roots. No synthetic CA, fixed remote IP, or TLS interception.
   try(SSLSocket tls=(SSLSocket)SSLContext.getDefault().getSocketFactory().createSocket(raw,"chatgpt.com",443,true)){
    SSLParameters sp=tls.getSSLParameters();sp.setEndpointIdentificationAlgorithm("HTTPS");sp.setServerNames(List.of(new SNIHostName("chatgpt.com")));sp.setProtocols(new String[]{"TLSv1.3","TLSv1.2"});tls.setSSLParameters(sp);tls.setSoTimeout(3000);tls.startHandshake();
    String path=URI.create(url).getRawPath();
    tls.getOutputStream().write(("GET "+path+" HTTP/1.1\r\nHost: chatgpt.com\r\nAccept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
    InputStream in=tls.getInputStream();String header=readHeader(in,8192,deadline);
    String[] lines=header.split("\r\n");
    if(!(lines[0].startsWith("HTTP/1.1 200 ")||lines[0].startsWith("HTTP/1.0 200 ")))throw new IOException("STATUS");
    Map<String,String> h=new HashMap<>();
    for(int n=1;n<lines.length;n++){
     int colon=lines[n].indexOf(':');if(colon<1)throw new IOException("HEADER");
     String name=lines[n].substring(0,colon).toLowerCase(Locale.ROOT),value=lines[n].substring(colon+1).trim();
     if(h.putIfAbsent(name,value)!=null&&Set.of("content-type","content-length","transfer-encoding","content-encoding","location").contains(name))throw new IOException("DUPLICATE_HEADER");
    }
    if(!h.getOrDefault("content-type","").toLowerCase(Locale.ROOT).startsWith("application/json")||h.containsKey("location")||!h.getOrDefault("content-encoding","identity").equalsIgnoreCase("identity"))throw new IOException("CONTENT");
    if(h.containsKey("transfer-encoding")&&h.containsKey("content-length"))throw new IOException("FRAMING");
    ByteArrayOutputStream body=new ByteArrayOutputStream();
    if(h.containsKey("transfer-encoding")){
     if(!"chunked".equalsIgnoreCase(h.get("transfer-encoding")))throw new IOException("TRANSFER");
     int chunks=0;
     while(true){
      if(++chunks>4096)throw new IOException("CHUNKS");String line=readLine(in,80,deadline);
      if(!line.matches("[0-9A-Fa-f]{1,8}"))throw new IOException("CHUNK_SIZE");
      long size=Long.parseLong(line,16);if(size>65536-body.size())throw new IOException("SIZE");
      if(size==0){if(!readLine(in,2,deadline).isEmpty())throw new IOException("TRAILER");break;}
      copy(in,body,(int)size,deadline);if(!readLine(in,2,deadline).isEmpty())throw new IOException("CHUNK_END");
     }
    }else if(h.containsKey("content-length")){
     String value=h.get("content-length");if(!value.matches("[0-9]{1,6}"))throw new IOException("LENGTH");int len=Integer.parseInt(value);if(len>65536)throw new IOException("SIZE");copy(in,body,len,deadline);
    }else{
     byte[] buf=new byte[4096];int n;while((n=in.read(buf))!=-1){checkDeadline(deadline);if(body.size()+n>65536)throw new IOException("SIZE");body.write(buf,0,n);}
    }
    return body.toByteArray();
   }
  }
 }
 static void checkDeadline(long deadline)throws IOException{if(System.nanoTime()>deadline)throw new IOException("DEADLINE");}
 static String readHeader(InputStream in,int max,long deadline)throws IOException{
  StringBuilder out=new StringBuilder();String line;
  while(!(line=readLine(in,max,deadline)).isEmpty()){
   if(out.length()+line.length()+2>max)throw new IOException("HEADER_SIZE");out.append(line).append("\r\n");
  }
  return out.toString();
 }
 static String readLine(InputStream in,int max,long deadline)throws IOException{
  ByteArrayOutputStream out=new ByteArrayOutputStream();int previous=-1;
  while(true){checkDeadline(deadline);int b=in.read();if(b<0)throw new EOFException();
   if(previous==13&&b==10){byte[] bytes=out.toByteArray();return new String(bytes,0,bytes.length-1,StandardCharsets.ISO_8859_1);}
   out.write(b);if(out.size()>max+2)throw new IOException("LINE_SIZE");previous=b;
  }
 }
 static void copy(InputStream in,ByteArrayOutputStream out,int len,long deadline)throws IOException{
  byte[] b=new byte[Math.min(4096,Math.max(1,len))];int left=len;
  while(left>0){checkDeadline(deadline);int n=in.read(b,0,Math.min(b.length,left));if(n<0)throw new EOFException();out.write(b,0,n);left-=n;}
 }
}
