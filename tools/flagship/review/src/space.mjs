import * as THREE from 'three';

export function makeSpace() {
  const space = new THREE.Group();
  let seed = 112;
  const rand = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
  const coords = [], colors = [];
  for (let i = 0; i < 1350; i++) {
    const z = rand() * 2 - 1, a = rand() * Math.PI * 2, r = Math.sqrt(1 - z * z);
    coords.push(Math.cos(a) * r * 200, z * 200, Math.sin(a) * r * 200);
    const power = .15 + rand() * .55;
    colors.push(power * .85, power * .93, power);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(coords, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  const stars = new THREE.Points(geometry, new THREE.PointsMaterial({ size: .13, vertexColors: true, depthWrite: false }));
  space.add(stars);
  const sun = new THREE.Vector3(-.32, .57, -.75).normalize();
  const vertexShader = `varying vec3 vNormal; varying vec3 vPosition;
    void main(){ vNormal=normalize(mat3(modelMatrix)*normal); vPosition=(modelMatrix*vec4(position,1.)).xyz; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`;
  const noise = `float hash(vec3 p){p=fract(p*.3183099+vec3(.1,.2,.3));p*=17.;return fract(p.x*p.y*p.z*(p.x+p.y+p.z));}
    float noise3(vec3 x){vec3 i=floor(x),f=fract(x);f=f*f*(3.-2.*f);return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
    float fbm(vec3 p){float a=.5,s=0.;for(int i=0;i<5;i++){s+=a*noise3(p);p=p*2.07+vec3(4.3,9.7,2.1);a*=.5;}return s;}`;
  const material = new THREE.ShaderMaterial({
    uniforms: { sun: { value: sun } }, vertexShader,
    fragmentShader: `varying vec3 vNormal; varying vec3 vPosition; uniform vec3 sun; ${noise}
      void main(){
        vec3 n=normalize(vNormal); float terrain=fbm(n*4.2+vec3(11.));
        float coast=smoothstep(.48,.54,terrain);
        vec3 ocean=vec3(.012,.056,.086),land=mix(vec3(.09,.12,.10),vec3(.30,.26,.18),smoothstep(.51,.74,terrain));
        vec3 albedo=mix(ocean,land,coast);
        float cloud=smoothstep(.52,.66,fbm(n*22.+fbm(n*5.)*2.));
        albedo=mix(albedo,vec3(.70,.76,.78),cloud*.82);
        float lighting=smoothstep(-.12,.8,dot(n,sun));
        float rim=pow(1.-max(0.,dot(n,normalize(cameraPosition-vPosition))),3.5);
        vec3 color=albedo*(.028+lighting*1.18)+vec3(.08,.30,.46)*rim*smoothstep(-.2,.5,dot(n,sun))*.46;
        gl_FragColor=vec4(color,1.);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`
  });
  const sphere = new THREE.SphereGeometry(22.3, 64, 40);
  const planet = new THREE.Mesh(sphere, material);
  // Preserve the source study's angular scale and direction, compress distance
  // solely for stable WebGL depth precision. This isn't a physical orbit model.
  planet.position.set(79.2, -29.6, -52.3);
  space.add(planet);
  const atmosphere = new THREE.Mesh(sphere, new THREE.ShaderMaterial({
    uniforms: { sun: { value: sun } }, vertexShader, transparent: true, depthWrite: false,
    side: THREE.BackSide, blending: THREE.AdditiveBlending,
    fragmentShader: `varying vec3 vNormal; varying vec3 vPosition; uniform vec3 sun;
      void main(){vec3 n=normalize(vNormal);float rim=pow(1.-abs(dot(n,normalize(cameraPosition-vPosition))),5.);float lit=smoothstep(-.25,.55,dot(n,sun));gl_FragColor=vec4(vec3(.12,.38,.65),rim*lit*.35);}`
  }));
  atmosphere.position.copy(planet.position); atmosphere.scale.setScalar(1.013); space.add(atmosphere);
  return space;
}
